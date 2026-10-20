"""Reproducible labelled synthetic comparison; no paid calls or target execution."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
SCOPE = {"PR-PY-001", "PR-FASTAPI-001", "PR-DOCKER-001", "PR-DOCKER-002", "PR-CI-001", "PR-CI-002", "PR-SECRET-001"}


def invoke(args):
    started = time.perf_counter()
    completed = subprocess.run([sys.executable, *args], capture_output=True, text=True, check=False, timeout=15)
    assert completed.returncode in {0, 2}, completed.stderr or completed.stdout
    return json.loads(completed.stdout), (time.perf_counter() - started) * 1000


def main():
    output = ROOT / ".mcp-products/inspector/benchmark"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        work = Path(temporary)
        scenarios = [
            ("composite_defect", ROOT / "examples/inspector/defective", {"PR-PY-001": 2, "PR-FASTAPI-001": 1, "PR-DOCKER-001": 1, "PR-DOCKER-002": 1, "PR-CI-001": 2, "PR-CI-002": 1}),
            ("composite_corrected", ROOT / "examples/inspector/corrected", {}),
        ]
        micro = {
            "comments": ('# debug=True reload=True\nx="--reload"\n', {}),
            "health_name_without_route": ('from fastapi import FastAPI\napp=FastAPI()\ndef health(): pass\n', {"PR-FASTAPI-001": 1}),
            "second_application": ('from fastapi import FastAPI\na=FastAPI()\nb=FastAPI()\n@a.get("/health")\ndef h(): pass\n', {"PR-FASTAPI-001": 1}),
            "uvicorn_alias": ('import uvicorn as server\nserver.run("app:app", reload=True)\n', {"PR-PY-001": 1}),
        }
        for name, (source, expected) in micro.items():
            directory = work / name
            directory.mkdir()
            (directory / "app.py").write_text(source)
            scenarios.append((name, directory, expected))
        rows = []
        for name, path, expected in scenarios:
            timings = {"inspector": [], "maintained_script": []}
            seen = []
            for _ in range(7):
                inspector, elapsed = invoke(["-m", "mcp_products.inspector", str(path), "--format", "json"])
                timings["inspector"].append(elapsed)
                assert inspector["metadata"]["complete"]
                observed = dict(Counter(item["id"] for item in inspector["findings"] if item["id"] in SCOPE))
                baseline, elapsed = invoke([str(ROOT / "benchmarks/inspector/review_baseline.py"), str(path)])
                timings["maintained_script"].append(elapsed)
                assert observed == expected and baseline == expected, (name, observed, baseline, expected)
                inspector.pop("generated_at")
                seen.append(hashlib.sha256(json.dumps(inspector, sort_keys=True).encode()).hexdigest())
            assert len(set(seen)) == 1
            rows.append({"scenario": name, "expected_common_scope": expected,
                         "inspector_matches": True, "maintained_script_matches": True,
                         "deterministic_repeats": len(seen),
                         "median_cli_ms": {name: round(statistics.median(values), 2) for name, values in timings.items()}})
        report = {"method": "six synthetic scenarios; seven CLI subprocess runs each; exact common-rule occurrence counts",
                  "provenance": "Baseline authored in this session by the same agent, not an independent review. AST + PyYAML safe_load + Docker stages; no Inspector imports.",
                  "limits": "No public-repository holdout, human review-time, production incident, calibrated accuracy or customer ROI evidence. Inspector starts an additional bounded worker; baseline trusts fixtures.",
                  "python": platform.python_version(), "platform": platform.platform(),
                  "pyyaml": importlib.metadata.version("PyYAML"),
                  "baseline_sha256": hashlib.sha256((ROOT / "benchmarks/inspector/review_baseline.py").read_bytes()).hexdigest(),
                  "rows": rows, "paid_model_calls": 0, "provider_cost": 0}
        (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
