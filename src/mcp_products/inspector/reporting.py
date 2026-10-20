from __future__ import annotations

from urllib.parse import quote

from .model import RULES, RULESET, VERSION
from .result import ProductResult

RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0, "none": 99}


def exit_code(result: ProductResult, *, fail_on: str = "high", new_only: bool = False) -> int:
    if fail_on not in {"high", "critical", "medium", "none"}:
        raise ValueError("invalid fail_on")
    if result.verdict in {"error", "incomplete", "unsupported"} or not result.metadata.get("complete"):
        return 5
    if new_only and "baseline" not in result.metadata:
        return 5
    return 2 if any(RANK[item.severity] >= RANK[fail_on] and (not new_only or item.status == "new") for item in result.findings) else 0


def to_sarif(result: ProductResult) -> dict:
    rules = [{"id": rule, "name": rule.replace("-", "_"), "shortDescription": {"text": title},
              "help": {"text": remediation}, "properties": {"ruleVersion": version}}
             for rule, (version, _, title, remediation) in RULES.items()]
    results = []
    for finding in result.findings:
        metadata = finding.metadata
        item = {
            "ruleId": finding.id, "ruleIndex": list(RULES).index(finding.id),
            "level": "error" if RANK[finding.severity] >= 3 else "warning",
            "message": {"text": finding.title + ". " + finding.evidence[0].fact},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": quote(metadata["path"], safe="/")},
                                                    "region": {"startLine": metadata["line"]}}}],
            "partialFingerprints": {"inspectorInstance/v1": metadata["instance_id"]},
            "properties": {"ruleVersion": metadata["rule_version"], "evidenceKind": metadata["evidence_kind"]},
        }
        if finding.status in {"new", "unchanged"}:
            item["baselineState"] = finding.status
        results.append(item)
    issues = result.metadata.get("issues", [])
    if result.verdict == "incomplete":
        issues = [*issues, {"code": "partial_static_coverage"}]
    return {"$schema": "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0-rtm.5.json",
            "version": "2.1.0", "runs": [{
                "tool": {"driver": {"name": "prodcheck", "version": VERSION,
                                     "semanticVersion": VERSION, "rules": rules}},
                "results": results,
                "invocations": [{"executionSuccessful": result.metadata.get("complete", False),
                                 "toolExecutionNotifications": [{"level": "error", "message": {"text": item["code"]}} for item in issues]}],
                "properties": {"rulesetVersion": RULESET, "coverage": result.coverage,
                               "verdict": result.verdict, "baseline": result.metadata.get("baseline")},
            }]}
