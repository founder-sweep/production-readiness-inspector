"""Public deterministic engine, isolated from target repositories."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from .model import PRODUCT, PROFILE, RULESET, Limits
from .result import Evidence, Finding, ProductResult


def error_result(code: str) -> ProductResult:
    return ProductResult(PRODUCT, "error", coverage={"repository": "not_analyzed"}, metadata={
        "profile": PROFILE, "ruleset_version": RULESET, "complete": False,
        "issues": [{"code": code, "path": "", "line": 1}],
    })


def inspect_repository(root: str | Path, baseline: dict | None = None, *, limits: Limits | None = None) -> ProductResult:
    """Read local supported inputs; never execute/import target code or use a network.

    Parsing runs in an isolated Python child with a hard wall-clock timeout and
    Linux resource limits. The timestamp is observational; other result fields
    are deterministic for an unchanged complete input and policy.
    """
    try:
        if not isinstance(root, (str, os.PathLike)) or not os.fspath(root) or "\0" in os.fspath(root):
            return error_result("invalid_path")
        if baseline is not None and not isinstance(baseline, dict):
            return error_result("invalid_baseline")
        if limits is not None and not isinstance(limits, Limits):
            return error_result("invalid_limits")
        limits = limits or Limits()
        request = json.dumps({"root": os.path.abspath(root), "baseline": baseline, "limits": asdict(limits)})
        if len(request.encode()) > 8_000_000:
            return error_result("request_size_limit")
        process = subprocess.run(
            [sys.executable, "-I", "-m", "mcp_products.inspector.worker"],
            input=request, capture_output=True, text=True,
            cwd=Path(__file__).resolve().parent, timeout=limits.max_seconds + 2, check=False,
        )
        if process.returncode:
            return error_result("analysis_worker_failed")
        payload = json.loads(process.stdout)
        payload["findings"] = [Finding(**{**item, "evidence": [Evidence(**evidence) for evidence in item["evidence"]]}) for item in payload["findings"]]
        return ProductResult(**payload)
    except subprocess.TimeoutExpired:
        return error_result("time_limit")
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        return error_result("invalid_request_or_worker_response")
