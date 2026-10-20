from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import error_result, inspect_repository
from .reporting import exit_code, to_sarif


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prodcheck", description="Static local Python/FastAPI, Docker and Actions evidence. No target code execution.")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--format", choices=("json", "text", "sarif"), default="text")
    parser.add_argument("--baseline", type=Path, help="Prior complete Inspector instance report")
    parser.add_argument("--new-only", action="store_true", help="Gate only new instances; requires --baseline")
    parser.add_argument("--fail-on", choices=("critical", "high", "medium", "none"), default="high")
    args = parser.parse_args(argv)
    result = None
    baseline = None
    if args.new_only and not args.baseline:
        result = error_result("new_only_requires_baseline")
    if args.baseline and result is None:
        try:
            with args.baseline.open("rb") as handle:
                data = handle.read(8_000_001)
            if len(data) > 8_000_000:
                raise ValueError
            baseline = json.loads(data)
            if not isinstance(baseline, dict):
                raise TypeError
        except (OSError, ValueError, TypeError):
            result = error_result("baseline_unreadable_or_invalid_json")
    result = result or inspect_repository(args.path, baseline)
    code = exit_code(result, fail_on=args.fail_on, new_only=args.new_only)
    if args.format in {"json", "sarif"}:
        print(json.dumps(to_sarif(result) if args.format == "sarif" else result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"{result.product}: {result.verdict} ({len(result.findings)} findings; exit {code})")
        print("Scope: static shipped rules only; declared health routes do not prove runtime health.")
        for finding in result.findings:
            print(f"[{finding.severity}/{finding.status}] {finding.id} {finding.title} ({finding.evidence[0].locator})")
            print(f"  {finding.remediation}")
        for issue in result.metadata.get("issues", []):
            print(f"[evaluation] {issue['code']} ({issue['path']}:{issue['line']})")
        print("Coverage: " + ", ".join(f"{key}={value}" for key, value in result.coverage.items()))
    return code
