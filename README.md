# Production Readiness Inspector

Give clients a clear record of what changed before their next Python release.
**[Start with the agency quickstart](docs/inspector/marketing/AGENCY_QUICKSTART.md)**:
published-release installation, a synthetic before/after example, and an HTML handoff.

Static Python/FastAPI, Docker and GitHub Actions evidence for your next release.
Run the local scanner free, keep source on your machine, and optionally save
private release reports with instance-level baseline history.

**[Open Inspector](https://inspector.contentsweep.ai/inspector)** — 3 free hosted
reports, then **$19 USD for 100 reports**. No subscription or automatic top-up.

## Install the free local CLI

Python 3.12 on Linux/Ubuntu WSL2 is qualified. Use a dedicated environment;
this distribution overlaps the Inspector namespace in the older MCPProducts suite.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-deps \
  https://inspector.contentsweep.ai/inspector/download/contentsweep_prodcheck-0.3.0-py3-none-any.whl
.venv/bin/prodcheck /path/to/application --format json > report.json
```

Download hashes are at the [release manifest](https://inspector.contentsweep.ai/inspector/download/manifest.json).
Direct HTTPS and GitHub releases are available. PyPI and registry publication
are not claimed.

Default CI exits: 0 when the configured finding threshold is clear, 2 for high
findings, 5 for failed/incomplete evaluation. `--fail-on medium|high|critical|none`
sets finding policy; evaluation errors always fail. `--baseline reviewed.json
--new-only` compares finding instances instead of collapsing rule IDs.

## Hosted release history

Save the workspace key privately before purchasing. It is the only workspace
credential; there is no email/password recovery. Three hosted reports are free.
Preview what will leave your machine:

```bash
.venv/bin/python -m mcp_products.inspector.cloud preview report.json
# Supply INSPECTOR_API_KEY privately, or use --key-file with a private key file:
.venv/bin/python -m mcp_products.inspector.cloud submit report.json --project my-service --key-file private-key-file
```

Only structured rule/version/instance identities, relative paths/lines, coverage
and fingerprints are submitted. Raw source, evidence prose and repository
archives are excluded. Review paths for sensitivity. The server preserves
caller-submitted evidence; it does not independently verify source or deployment.

One new complete hosted report uses one credit. Exact retries reuse their
receipt without another credit. Unsupported/incomplete inputs and platform
failures are free. Hosted reports include new/unchanged/resolved instance
comparisons, 30-day private history and HTML/JSON exports. Credits do not expire.
See the product's [terms, privacy and refund policy](https://inspector.contentsweep.ai/inspector#terms).

## Supported scope

- Literal FastAPI debug / Uvicorn reload and directly declared conventional GET
  health routes; route declarations do not prove runtime health.
- Docker external base digests, final explicit user, startup command form and
  development reload. Internal build stages are distinguished from runtime.
- Supported YAML/JSON workflow declarations, action references and permission
  scope; comments and run strings do not become action findings.
- Bounded, read-only traversal with ignore rules and symlink/private-file
  exclusions; parsing runs in a resource-limited child. No target code is imported
  or executed and local scans make no network/model calls.

Dynamic settings and unsupported syntax disclose incomplete coverage. Broader
YAML, cross-file router resolution, Compose/Kubernetes, CVEs, general secrets
and runtime readiness are outside this beta. No score, certification, accuracy
percentage or incident-prevention guarantee is claimed.

## Local MCP and verification

```bash
.venv/bin/python -m pip install 'mcp==2.3.0'
.venv/bin/python -m mcp_products.inspector.mcp --root /approved/local/repository
```

The official-SDK stdio server exposes the same offline inspection engine. Hosted
submission is explicit through the cloud CLI/REST API; it never happens during
a local scan. Workspace purchase accounting is independent of other products.

To run the owned tests from a source checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[hosted,mcp]' pytest==9.1.1 httpx==0.28.1
.venv/bin/python -m pytest tests/test_inspector_engine.py tests/test_inspector_interfaces.py tests/test_inspector_commerce.py
```

[Rule contract and primary sources](docs/inspector/RULES.md) ·
[Hosted operating record](docs/inspector/HOSTED_LAUNCH.md) ·
[Synthetic benchmark method](benchmarks/inspector/README.md).
Synthetic correctness parity with a maintained script is not independent
accuracy, customer ROI or paid adoption evidence.

Apache-2.0. Content Sweep LLC. Billing/support: founder@contentsweep.ai.
