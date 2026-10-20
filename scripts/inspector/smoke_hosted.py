#!/usr/bin/env python3
"""Real HTTPS metadata flow. Synthetic internal workspaces; never a payment."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from deploy import remote
from setup_stripe import private_write

from mcp_products.inspector import inspect_repository
from mcp_products.inspector.commerce import summarize_report

BASE = "https://inspector.contentsweep.ai/inspector"


def call(path, *, key=None, method="GET", body=None, expected=200):
    headers = {}
    if key:
        headers["Authorization"] = "Bearer " + key
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        response = urlopen(request, timeout=30)
    except HTTPError as exc:
        response = exc
    data = response.read()
    assert response.status == expected, (path, response.status)
    return json.loads(data) if "json" in response.headers.get("Content-Type", "") else data


def main():
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    runtime = root / ".mcp-products/inspector"
    healthy = None
    for _ in range(30):
        try:
            healthy = call("/health")
            break
        except OSError:
            time.sleep(2)
    assert healthy and healthy["ready"]
    page = call("").decode()
    assert "$19" in page and "No application-source upload" in page
    assert call("/download/contentsweep_prodcheck-0.3.0-py3-none-any.whl").startswith(b"PK")
    path = runtime / "https-workspaces.private.json"
    workspaces = json.loads(path.read_text()) if path.exists() else []
    while len(workspaces) < 2:
        workspaces.append(call("/api/workspaces", method="POST", body={}))
        private_write(path, json.dumps(workspaces, indent=2))
    ids = [item["workspace_id"] for item in workspaces]
    # Explicitly classify operator-created workspaces before any purchase.
    code = "import os,sqlite3; d=sqlite3.connect(os.environ['INSPECTOR_DATABASE']); d.executemany(\"UPDATE workspaces SET classification='internal' WHERE id=?\", " + repr([(value,) for value in ids]) + "); d.commit(); print('internal-classification-saved')"
    remote(root, "import subprocess\np=subprocess.run(['docker','exec','--user','10001','contentsweep-inspector-api','python','-c'," + repr(code) + "],capture_output=True,text=True,check=True)\nprint(p.stdout)")
    key, other = (item["api_key"] for item in workspaces)
    first = summarize_report(inspect_repository(root / "examples/inspector/defective").to_dict())
    fixed = summarize_report(inspect_repository(root / "examples/inspector/corrected").to_dict())
    body = {"project": "internal-qualification", "idempotency_key": "https-defect-0.3", "summary": first}
    report = call("/api/reports", key=key, method="POST", body=body)
    retry = call("/api/reports", key=key, method="POST", body=body)
    assert report["id"] == retry["id"] and retry["billed_reports"] == 0
    body = {"project": "internal-qualification", "idempotency_key": "https-corrected-0.3", "summary": fixed}
    corrected = call("/api/reports", key=key, method="POST", body=body)
    assert len(corrected["comparison"]["resolved"]) == len(first["findings"])
    call("/api/reports/" + report["id"], key=other, expected=404)
    call("/api/balance", expected=401)
    balance = call("/api/balance", key=key)
    assert balance["reports_remaining"] == 1
    invalid = dict(first, source="MUST_NOT_BE_STORED")
    call("/api/reports", key=key, method="POST", body={"project": "internal-qualification", "idempotency_key": "https-invalid-0.3", "summary": invalid}, expected=422)
    assert call("/api/balance", key=key) == balance
    output = call("/api/reports/" + report["id"] + "/html", key=key).decode()
    assert "PR-PY-001" in output
    assert len(call("/api/reports", key=key)["reports"]) == 2
    result = {"base_url": BASE, "release": healthy["release"], "https_reports_passed": True,
              "valid_tls": True, "trial_flow": True, "duplicate_retry_free": True,
              "baseline_resolved_instances": len(first["findings"]), "tenant_isolation": True,
              "invalid_summary_free": True, "html_export": True, "direct_wheel_download": True,
              "internal_workspaces": ids, "billing_enabled": healthy["billing_enabled"],
              "customer_charge_created": False, "independent_customer_evidence": False}
    private_write(runtime / "qualification/commercial-https.private.json", json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
