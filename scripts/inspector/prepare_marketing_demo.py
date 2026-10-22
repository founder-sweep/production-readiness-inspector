#!/usr/bin/env python3
"""Capture a synthetic demonstration using the published wheel and existing API."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from deploy import remote
from smoke_hosted import call


def main():
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    runtime = root / ".mcp-products/inspector/marketing"
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    assets = root / "docs/inspector/marketing/assets"
    assets.mkdir(parents=True, exist_ok=True)
    wheel_name = "contentsweep_prodcheck-0.3.0-py3-none-any.whl"
    wheel = call("/download/" + wheel_name)
    manifest = call("/download/manifest.json")
    sha = hashlib.sha256(wheel).hexdigest()
    assert sha == manifest["artifacts"][wheel_name]
    (runtime / wheel_name).write_bytes(wheel)
    environment = runtime / "published-env"
    if not environment.exists():
        subprocess.run(["python3", "-m", "venv", str(environment)], check=True)
    subprocess.run([str(environment / "bin/python"), "-m", "pip", "install", "--no-index", "--no-deps", "--force-reinstall", str(runtime / wheel_name)], check=True, stdout=subprocess.DEVNULL)
    before_path = runtime / "before.json"
    after_path = runtime / "after.json"
    for fixture, target in (("defective", before_path), ("corrected", after_path)):
        args = [str(environment / "bin/prodcheck"), str(root / "examples/inspector" / fixture), "--format", "json", "--fail-on", "none"]
        if fixture == "corrected":
            args += ["--baseline", str(before_path)]
        result = subprocess.run(args, capture_output=True, check=True, timeout=30)
        target.write_bytes(result.stdout)
    program = "from mcp_products.inspector.commerce import summarize_report; import json,sys; print(json.dumps(summarize_report(json.load(sys.stdin))))"
    summaries = []
    for path in (before_path, after_path):
        result = subprocess.run([str(environment / "bin/python"), "-c", program], input=path.read_bytes(), capture_output=True, check=True)
        summaries.append(json.loads(result.stdout))
    credentials = json.loads((root / ".mcp-products/inspector/https-workspaces.private.json").read_text())[1]
    workspace_id = credentials["workspace_id"]
    query = "import sqlite3; db=sqlite3.connect(\"file:/data/inspector-live.sqlite?mode=ro\",uri=True); print(db.execute(\"SELECT classification FROM workspaces WHERE id=?\",(" + repr(workspace_id) + ",)).fetchone()[0])"
    code = "import subprocess\np=subprocess.run(" + repr(["docker", "exec", "contentsweep-inspector-api", "python", "-c", query]) + ",capture_output=True,text=True,check=True)\nprint(p.stdout)"
    assert remote(root, code).strip() == "internal", "Only a preclassified internal workspace is allowed"
    reports = []
    for label, summary in zip(("before", "after"), summaries, strict=True):
        body = {"project": "synthetic-agency-demo", "idempotency_key": "marketing-v030-" + label, "summary": summary}
        report = call("/api/reports", key=credentials["api_key"], method="POST", body=body)
        reports.append(report)
        page = call("/api/reports/" + report["id"] + "/html", key=credentials["api_key"])
        (assets / (label + "-handoff.html")).write_bytes(page)
        (assets / (label + "-summary.json")).write_text(json.dumps(summary, indent=2) + "\n")
    assert len(summaries[0]["findings"]) == 10 and not summaries[1]["findings"]
    assert len(reports[0]["comparison"]["new"]) == 10
    assert len(reports[1]["comparison"]["resolved"]) == 10
    assert not reports[1]["comparison"]["new"] and not reports[1]["comparison"]["unchanged"]
    public = {"synthetic": True, "product_version": "0.3.0", "wheel_sha256": sha,
              "ruleset": summaries[0]["ruleset_version"], "real_https_flow": True,
              "before": {"findings": 10, "new": 10, "unchanged": 0, "resolved": 0},
              "after": {"findings": 0, "new": 0, "unchanged": 0, "resolved": 10},
              "raw_source_uploaded": False, "paid_purchase_created": False,
              "internal_workspace_excluded_from_customer_metrics": True}
    (assets / "demonstration.json").write_text(json.dumps(public, indent=2) + "\n")
    (runtime / "demonstration.private.json").write_text(json.dumps({"reports": [r["id"] for r in reports], "evidence": public}, indent=2))
    os.chmod(runtime / "demonstration.private.json", 0o600)
    print(json.dumps(public, indent=2))


if __name__ == "__main__":
    main()
