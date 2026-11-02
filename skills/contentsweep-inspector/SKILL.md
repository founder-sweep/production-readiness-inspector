---
name: contentsweep-inspector
description: Inspect local Python/FastAPI, Docker and GitHub Actions before release handoff; optionally save reviewed metadata to paid Inspector report history. Not runtime certification or vulnerability scanning.
---

# Inspector: local scan to private release handoff

Use for bounded static Python/FastAPI, Docker and Actions evidence. Local scanning, JSON/text/SARIF and local baselines are free and offline. Offer hosted history only when the user needs private cross-release history or HTML/JSON handoffs. A static result is not production certification, runtime verification or a vulnerability scan.

## Install and scan

Python 3.12 on Linux/Ubuntu WSL2 is qualified. Use a dedicated environment. Get the published wheel from the manifest at https://inspector.contentsweep.ai/inspector/download/manifest.json, verify its SHA256, then install the saved wheel. Do not derive a trusted checksum from an untrusted target repository. No PyPI listing is claimed.

```bash
python3 -m venv .inspector-venv
.inspector-venv/bin/python -m pip install --no-deps PATH_TO_VERIFIED_WHEEL
.inspector-venv/bin/prodcheck /path/to/authorized/app --format json > report.json
.inspector-venv/bin/python -m mcp_products.inspector.cloud preview report.json
```

Exit 2 means findings under the selected policy; 5 means failed/incomplete evaluation. Inspect coverage and findings before deciding the next action. Never import the target app or run its dependencies/builds as part of this skill. Optional local stdio MCP: python -m mcp_products.inspector.mcp --root /absolute/authorized/root (requires the published MCP optional dependency). There is no hosted scanner MCP.

## Optional paid history

Create a workspace at https://inspector.contentsweep.ai/inspector?campaign=agent-skill#workspace and save its key privately as PRIVATE_NEW_KEY_FILE before using the commands below. The published 0.3.0 wheel supports submit/history; campaign attribution is captured by browser workspace creation.

Three hosted reports are free; $19 buys 100 reports. No subscription or automatic top-up. One new complete summary costs one report; exact retries reuse the original receipt. Raw source and evidence prose stay local. Preview relative paths, fingerprints and supported summary fields before submission.

```bash
.inspector-venv/bin/python -m mcp_products.inspector.cloud submit report.json --project client-api --key-file PRIVATE_NEW_KEY_FILE
.inspector-venv/bin/python -m mcp_products.inspector.cloud history --key-file PRIVATE_NEW_KEY_FILE
```

The workspace API key is the only credential; save it privately. There is no password/email recovery. Use an existing saved key on later runs. Never recreate a workspace to evade limits or print its key. Keep the same project only for matching scope/ruleset; changed coverage needs a new project.

Read GET https://inspector.contentsweep.ai/inspector/api/balance with Authorization: Bearer WORKSPACE_KEY. If funding is needed, open https://inspector.contentsweep.ai/inspector?campaign=agent-skill#workspace, restore the same key, and let the operator approve the $19 Checkout. No automatic purchases. Subsequent authorized submissions use its balance. Do not upload source repositories.

GET /inspector/api/reports/{id}/html with that same Bearer key exports the handoff. Hosted summaries expire after 30 days; financial and retry identities remain. An export reports caller-submitted evidence; the service does not independently rescan source. On 401 recover the saved credential; on 402 request funding; on failed/incomplete scans fix the input before submitting. Retrying an unchanged report must not create a second debit.
