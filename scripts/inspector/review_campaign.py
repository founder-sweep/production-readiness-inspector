#!/usr/bin/env python3
"""Read Inspector-only aggregate activity; retain no keys or customer identifiers."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path
from urllib.request import urlopen

from deploy import remote
from setup_stripe import private_write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", required=True, help="Client-local calendar date, YYYY-MM-DD")
    args = parser.parse_args()
    date = dt.date.fromisoformat(args.as_of)
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    program = """import json,sqlite3
db=sqlite3.connect("file:/data/inspector-live.sqlite?mode=ro",uri=True)
def scalar(sql):return db.execute(sql,("customer",)).fetchone()[0]
result={
 "customer_workspaces":scalar("SELECT count(*) FROM workspaces WHERE classification=?"),
 "customer_workspaces_with_reports":scalar("SELECT count(DISTINCT r.workspace) FROM reports r JOIN workspaces w ON r.workspace=w.id WHERE w.classification=?"),
 "customer_paid_packs":scalar("SELECT count(*) FROM purchases WHERE classification=? AND granted>0"),
 "customer_paid_workspaces":scalar("SELECT count(DISTINCT workspace) FROM purchases WHERE classification=? AND granted>0 AND refunded_cents<1900"),
 "customer_gross_cents":1900*scalar("SELECT count(*) FROM purchases WHERE classification=? AND granted>0"),
 "customer_refunded_cents":scalar("SELECT coalesce(sum(refunded_cents),0) FROM purchases WHERE classification=? AND granted>0"),
 "customer_workspaces_with_later_reports":scalar("SELECT count(DISTINCT workspace) FROM (SELECT r.workspace,r.project FROM reports r JOIN workspaces w ON r.workspace=w.id WHERE w.classification=? GROUP BY r.workspace,r.project HAVING count(*)>=2 AND max(r.created)-min(r.created)>=86400)")}
print(json.dumps(result))
"""
    command = ["docker", "exec", "contentsweep-inspector-api", "python", "-c", program]
    code = "import subprocess\np=subprocess.run(" + repr(command) + ",capture_output=True,text=True,check=True)\nprint(p.stdout)"
    result = json.loads(remote(root, code))
    with urlopen("https://inspector.contentsweep.ai/inspector/health", timeout=20) as response:
        health = json.load(response)
    result.update({"as_of_client_date": date.isoformat(), "client_timezone": "America/New_York",
                   "scope": "Product aggregate to date; excludes internal workspaces and purchases. Campaign company attribution is manual.",
                   "live_service_ready": health["ready"], "live_billing_enabled": health["billing_enabled"],
                   "independent_buying_companies": 0 if result["customer_paid_packs"] == 0 else None,
                   "independent_company_measurement": "Confirm distinct outside firms in the private workbook; anonymous workspace counts are not company counts.",
                   "agent_messages_sent": 0, "new_marketing_spend_usd": 0})
    folder = root / ".mcp-products/inspector/marketing/reviews"
    private_write(folder / (date.isoformat() + ".private.json"), json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
