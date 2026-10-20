"""Private scanner worker. Parent imposes wall time even during parser work."""
from __future__ import annotations

import json
import re
import sys

from .docker_rules import DockerError, inspect_docker
from .model import BASELINE_FORMAT, PRODUCT, PROFILE, RULES, RULESET, Analysis, Limits
from .repository import Repository
from .result import ProductResult
from .workflow import WorkflowError, inspect_workflow


def compare_baseline(result: ProductResult, baseline: dict):
    metadata = result.metadata
    old_metadata = baseline.get("metadata", {})
    valid = (
        baseline.get("product") == PRODUCT
        and isinstance(old_metadata, dict)
        and old_metadata.get("baseline_format") == BASELINE_FORMAT
        and old_metadata.get("ruleset_version") == RULESET
        and old_metadata.get("scope_fingerprint") == metadata["scope_fingerprint"]
        and old_metadata.get("complete") is True
        and isinstance(baseline.get("findings"), list)
        and len(baseline["findings"]) <= 5000
    )
    old = {}
    if valid:
        for item in baseline["findings"]:
            if not isinstance(item, dict) or item.get("id") not in RULES or not isinstance(item.get("metadata"), dict):
                valid = False
                break
            instance = item["metadata"].get("instance_id", "")
            if not isinstance(instance, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", instance) or instance in old or item["metadata"].get("rule_version") != RULES[item["id"]][0]:
                valid = False
                break
            old[instance] = item["id"]
    if not valid:
        metadata["issues"].append({"code": "incompatible_or_invalid_baseline", "path": "", "line": 1})
        metadata["complete"] = False
        result.verdict = "error"
        return
    current = {item.metadata["instance_id"] for item in result.findings}
    for item in result.findings:
        item.status = "unchanged" if item.metadata["instance_id"] in old else "new"
    metadata["baseline"] = {
        "new_instances": sorted(current - old.keys()),
        "unchanged_instances": sorted(current & old.keys()),
        "resolved_instances": sorted(old.keys() - current) if metadata["complete"] else [],
        "resolution_evaluated": metadata["complete"],
    }


def scan(root: str, baseline: dict | None, limits: Limits) -> ProductResult:
    from .python_rules import inspect_python

    analysis = Analysis(max_findings=limits.max_findings)
    repository = Repository(root, limits, analysis)
    analyzed = 0
    for path, family, data in repository.collect():
        repository.check_time()
        state = "analyzed"
        try:
            if family == "environment":
                analysis.emit("PR-SECRET-001", path, 1, "A nonignored environment file exists. Contents and tracking status were not inspected.", "presence", inference=True)
                state = "presence_only"
            elif family == "python":
                inspect_python(data, path, analysis)
                analyzed += 1
            else:
                text = data.decode("utf-8")
                if family == "docker":
                    inspect_docker(text, path, analysis)
                else:
                    inspect_workflow(text, path, analysis)
                analyzed += 1
        except SyntaxError as exc:
            analysis.issue("python_parse_error", path, exc.lineno or 1)
            state = "parse_error"
        except (WorkflowError, DockerError) as exc:
            analysis.issue(exc.code, path, exc.line)
            state = "unsupported_or_invalid"
        except UnicodeError:
            analysis.issue("unsupported_encoding", path)
            state = "parse_error"
        except (ValueError, RecursionError, MemoryError):
            analysis.issue("parser_limit_or_evaluation_failure", path)
            state = "evaluation_error"
        if state not in {"analyzed", "presence_only"}:
            analysis.coverage[family] = "partial"
        analysis.file_states.append({"path": path, "family": family, "state": state})
    supported = repository.files > 0
    partial = any(value == "partial" for key, value in analysis.coverage.items() if key != "repository")
    complete = not analysis.issues and not partial and supported
    if not supported and not analysis.issues:
        analysis.issue("no_supported_input")
    if not complete:
        analysis.coverage["repository"] = "partial" if supported else "not_analyzed"
    verdict = "error" if analysis.issues else "incomplete" if not complete else "needs_review" if analysis.findings else "ready"
    metadata = {
        "profile": PROFILE, "ruleset_version": RULESET, "baseline_format": BASELINE_FORMAT,
        "complete": complete, "files_analyzed": analyzed, "files_considered": repository.files,
        "bytes_read": repository.bytes, "entries_visited": repository.entries,
        "skipped_counts": dict(sorted(repository.skipped.items())),
        "issues": analysis.issues, "notes": analysis.notes, "rule_states": analysis.rule_states,
        "file_states": analysis.file_states, "scope_fingerprint": repository.scope_fingerprint,
        "verdict_meaning": "Findings and coverage for shipped static rules only; ready is not a production certification.",
    }
    from .model import public_path
    for item in metadata["file_states"]:
        item["path"] = public_path(item["path"])
    result = ProductResult(PRODUCT, verdict, analysis.findings, analysis.coverage,
                           input_fingerprint="sha256:" + repository.hash.hexdigest(), metadata=metadata)
    if baseline is not None:
        compare_baseline(result, baseline)
    return result


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read(8_000_001))
        limits = Limits(**payload["limits"])
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (limits.max_seconds + 1, limits.max_seconds + 1))
        resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        result = scan(payload["root"], payload["baseline"], limits)
    except TimeoutError:
        from .engine import error_result
        result = error_result("time_limit")
    except Exception:  # noqa: BLE001 - isolated boundary must never print source-bearing parser errors
        # Parser messages can include raw source. Only fixed issue codes cross
        # this boundary, including unexpected errors. No traceback/source log.
        from .engine import error_result
        result = error_result("analysis_worker_failed")
    print(json.dumps(result.to_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
