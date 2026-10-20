from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from mcp_products.inspector import Limits, inspect_repository
from mcp_products.inspector.reporting import exit_code, to_sarif

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples/inspector"
DIGEST = "@sha256:" + "a" * 64


def scan_file(tmp_path, name, text):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return inspect_repository(tmp_path)


def ids(result):
    return [item.id for item in result.findings]


def test_composite_defect_and_correction_have_exact_evidence():
    bad, good = (inspect_repository(FIXTURES / name) for name in ("defective", "corrected"))
    assert bad.metadata["complete"] and good.metadata["complete"]
    assert len(bad.findings) == 10
    assert not good.findings
    assert good.verdict == "ready"
    assert exit_code(bad) == 2 and exit_code(good) == 0
    for finding in bad.findings:
        evidence = finding.metadata
        path = FIXTURES / "defective" / evidence["path"]
        assert 0 < evidence["line"] <= len(path.read_text().splitlines())
        assert finding.evidence[0].excerpt is None
        assert finding.remediation and evidence["rule_version"]


@pytest.mark.parametrize("text, expected", [
    ('# debug=True\ntext="reload=True --reload"\n', []),
    ('def other(debug=True): pass\nother(debug=True)\n', []),
    ('from other import FastAPI\napp=FastAPI(debug=True)\n', []),
    ('from fastapi import FastAPI as F\na=F(debug=True)\n', ["PR-PY-001", "PR-FASTAPI-001"]),
    ('import uvicorn as u\nu.run("app:app", reload=True)\n', ["PR-PY-001"]),
    ('import uvicorn\ndef f(uvicorn):\n uvicorn.run(reload=True)\n', []),
    ('from fastapi import FastAPI\ndef f(FastAPI):\n a=FastAPI(debug=True)\n', []),
    ('from fastapi import FastAPI\nFastAPI=lambda **kw: None\na=FastAPI(debug=True)\n', []),
])
def test_python_alias_scope_and_false_positive_cases(tmp_path, text, expected):
    result = scan_file(tmp_path, "app.py", text)
    assert ids(result) == expected


@pytest.mark.parametrize("route, absent, bad_status", [
    ('def health(): pass', True, False),
    ('a.get("/health")', True, False),
    ('@a.get("/health")\ndef x(): pass', False, False),
    ('@a.post("/health")\ndef x(): pass', True, False),
    ('@a.api_route("/health", methods=["POST"])\ndef x(): pass', True, False),
    ('@a.api_route("/health", methods=["GET"])\ndef x(): pass', False, False),
    ('@a.get("/health", status_code=503)\ndef x(): pass', False, True),
    ('a.add_api_route("/ready", endpoint=lambda: None)', False, False),
])
def test_route_evidence_is_registered_per_application(tmp_path, route, absent, bad_status):
    result = scan_file(tmp_path, "app.py", 'from fastapi import FastAPI\na=FastAPI()\n' + route + '\n')
    assert ("PR-FASTAPI-001" in ids(result)) == absent
    assert ("PR-FASTAPI-002" in ids(result)) == bad_status


def test_one_app_health_does_not_hide_another_app(tmp_path):
    result = scan_file(tmp_path, "app.py", 'from fastapi import FastAPI\na=FastAPI()\nb=FastAPI()\n@a.get("/health")\ndef x(): pass\n')
    assert ids(result) == ["PR-FASTAPI-001"]
    assert result.findings[0].metadata["line"] == 3


@pytest.mark.parametrize("text, expected", [
    (f"FROM python{DIGEST} AS build\nUSER root\nFROM scratch\nUSER 5\n", []),
    (f"FROM python{DIGEST} AS build\nUSER 0:0\nFROM build\n", ["PR-DOCKER-002"]),
    (f"FROM --platform=linux/amd64 python{DIGEST}\nCMD [\"uvicorn\", \"app:app\"]\n", []),
    ("FROM scratch\nCMD echo hi\n", ["PR-DOCKER-003"]),
    ("FROM scratch\nCMD exec uvicorn app:app\n", []),
    ('FROM scratch\nENTRYPOINT ["uvicorn"]\nCMD ["app:app", "--reload"]\n', ["PR-DOCKER-004"]),
])
def test_docker_final_stage_and_command_applicability(tmp_path, text, expected):
    result = scan_file(tmp_path, "Dockerfile", text)
    assert result.metadata["complete"]
    assert ids(result) == expected


def test_workflow_rules_use_structural_fields_not_run_strings(tmp_path):
    text = 'permissions: {contents: read}\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n          echo "uses: owner/repo@main"\n          echo "permissions: write-all"\n        env:\n          X: value\n      - uses: ./local\n      - uses: docker://alpine' + DIGEST + '\n'
    result = scan_file(tmp_path, ".github/workflows/ci.yml", text)
    assert result.metadata["complete"]
    assert not result.findings


@pytest.mark.parametrize("name, text, issue", [
    ("app.py", "def broken(:\n", "python_parse_error"),
    ("Dockerfile", "FROM scratch\nCMD [oops]\n", "docker_exec_json"),
    ("Dockerfile", "FROM scratch\nRUN <<EOF\nUSER root\nEOF\n", "docker_heredoc_unsupported"),
    (".github/workflows/ci.yml", "jobs: {}\njobs: {}\n", "yaml_duplicate_key"),
    (".github/workflows/ci.yml", "jobs: &a {}\n", "yaml_alias_tag_or_merge_unsupported"),
])
def test_parse_and_unsupported_failures_do_not_pass(tmp_path, name, text, issue):
    result = scan_file(tmp_path, name, text)
    assert not result.metadata["complete"]
    assert issue in {item["code"] for item in result.metadata["issues"]}
    assert exit_code(result, fail_on="none") == 5


def test_dynamic_config_is_partial_not_guessed(tmp_path):
    result = scan_file(tmp_path, "app.py", 'from fastapi import FastAPI\napp=FastAPI(debug=settings.DEBUG)\n')
    assert result.verdict == "incomplete" and exit_code(result) == 5
    assert "PR-PY-001" not in ids(result)


def test_safe_input_and_fingerprint_boundaries(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text('raise RuntimeError("MUST_NOT_EXECUTE")\n')
    outside = tmp_path / "outside.py"
    outside.write_text("MUST_NOT_READ_OUTSIDE")
    (repo / "outside.py").symlink_to(outside)
    (repo / "secrets").mkdir()
    (repo / "secrets/token.py").write_text("MUST_NOT_READ_SECRET")
    (repo / ".credentials.py").write_text("MUST_NOT_READ_HIDDEN")
    (repo / ".env").write_text("TOKEN=MUST_NOT_READ_ENV")
    first = inspect_repository(repo)
    (repo / ".env").write_text("different value")
    outside.write_text("different outside")
    second = inspect_repository(repo)
    assert first.input_fingerprint == second.input_fingerprint
    assert first.metadata["bytes_read"] == len((repo / "app.py").read_bytes())
    serialized = json.dumps(first.to_dict())
    assert "MUST_NOT" not in serialized
    assert "PR-SECRET-001" in ids(first)
    link = tmp_path / "link"
    link.symlink_to(repo, target_is_directory=True)
    assert inspect_repository(link).verdict == "error"
    assert inspect_repository(link / "app.py").verdict == "error"


def test_nested_ignore_negation_and_fingerprint_scope(tmp_path):
    (tmp_path / ".gitignore").write_text("*.py\n!keep.py\n.env\n")
    (tmp_path / "drop.py").write_text("invalid source")
    (tmp_path / "keep.py").write_text("x=1\n")
    (tmp_path / ".env").write_text("SECRET")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / ".prodcheckignore").write_text("Dockerfile\n")
    (nested / "Dockerfile").write_text("invalid")
    result = inspect_repository(tmp_path)
    assert result.verdict == "ready"
    assert result.metadata["files_analyzed"] == 1
    assert result.metadata["skipped_counts"]["ignored"] == 3


@pytest.mark.parametrize("limits", [Limits(max_file_bytes=8), Limits(max_total_bytes=8), Limits(max_files=1), Limits(max_entries=1), Limits(max_findings=1)])
def test_budgets_fail_explicitly(tmp_path, limits):
    for name in ("a.py", "b.py"):
        (tmp_path / name).write_text("from fastapi import FastAPI\na=FastAPI(debug=True)\n")
    result = inspect_repository(tmp_path, limits=limits)
    assert result.verdict == "error" and exit_code(result) == 5


def test_baseline_instances_survive_line_edits_and_report_new_and_resolved(tmp_path):
    file = tmp_path / "app.py"
    source = 'import uvicorn\nuvicorn.run("app:a", reload=True)\n'
    file.write_text(source)
    baseline = inspect_repository(tmp_path).to_dict()
    file.write_text("\n\n" + source + 'uvicorn.run("app:b", reload=True)\n')
    changed = inspect_repository(tmp_path, baseline)
    assert [item.status for item in changed.findings] == ["unchanged", "new"]
    assert len(changed.metadata["baseline"]["new_instances"]) == 1
    file.write_text("\n" + source)
    same = inspect_repository(tmp_path, baseline)
    assert exit_code(same, new_only=True) == 0
    file.write_text("x=1\n")
    fixed = inspect_repository(tmp_path, baseline)
    assert len(fixed.metadata["baseline"]["resolved_instances"]) == 1


def test_partial_baseline_does_not_claim_resolution_or_hide_errors(tmp_path):
    file = tmp_path / "app.py"
    file.write_text('import uvicorn\nuvicorn.run("app:a", reload=True)\n')
    baseline = inspect_repository(tmp_path).to_dict()
    file.write_text("def invalid(:")
    result = inspect_repository(tmp_path, baseline)
    assert not result.metadata["baseline"]["resolution_evaluated"]
    assert not result.metadata["baseline"]["resolved_instances"]
    assert exit_code(result, new_only=True) == 5
    assert inspect_repository(tmp_path, {"findings": [{"id": "PR-PY-001"}]}).verdict == "error"


def test_cli_errors_and_sarif_preserve_evaluation_failure(tmp_path):
    bad_baseline = tmp_path / "old.json"
    bad_baseline.write_text("invalid")
    for args in ([str(tmp_path / "missing")], [str(tmp_path), "--baseline", str(bad_baseline)], [str(tmp_path), "--new-only"]):
        process = subprocess.run([sys.executable, "-m", "mcp_products.inspector", *args, "--format", "json"], text=True, capture_output=True, check=False)
        assert process.returncode == 5
        assert json.loads(process.stdout)["verdict"] == "error"
        assert "Traceback" not in process.stderr
    sarif = to_sarif(inspect_repository(tmp_path / "missing"))
    assert sarif["version"] == "2.1.0"
    assert not sarif["runs"][0]["invocations"][0]["executionSuccessful"]


@pytest.mark.parametrize("baseline", ["null", "[]", "17"])
def test_explicit_cli_baseline_must_be_an_object(tmp_path, baseline):
    file = tmp_path / "baseline.json"
    file.write_text(baseline)
    process = subprocess.run([sys.executable, "-m", "mcp_products.inspector", str(FIXTURES / "corrected"), "--baseline", str(file), "--format", "json"], capture_output=True, text=True, check=False)
    assert process.returncode == 5
    assert json.loads(process.stdout)["metadata"]["issues"][0]["code"] == "baseline_unreadable_or_invalid_json"


def test_baseline_policy_change_requires_review(tmp_path):
    (tmp_path / "app.py").write_text("x=1\n")
    old = inspect_repository(tmp_path).to_dict()
    (tmp_path / ".prodcheckignore").write_text("generated/\n")
    result = inspect_repository(tmp_path, old)
    assert result.verdict == "error"
    assert result.metadata["issues"][-1]["code"] == "incompatible_or_invalid_baseline"
