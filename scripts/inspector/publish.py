#!/usr/bin/env python3
"""Publish an Inspector-only allowlisted source repository and release artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

REPOSITORY = "founder-sweep/production-readiness-inspector"
PUBLIC_README = """# Production Readiness Inspector

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
.venv/bin/python -m pip install --no-deps \\
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
"""


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, check=False, timeout=120)
    if result.returncode:
        raise RuntimeError("publication command failed; credentials/output withheld")
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path(command(["git", "rev-parse", "--show-toplevel"]))
    folder = root / ".mcp-products/inspector/publication"
    payload = folder / "payload"
    payload.mkdir(parents=True, exist_ok=True)
    selected = {}
    for base in ["src/mcp_products/inspector", "examples/inspector", "integrations/inspector", "benchmarks/inspector", "scripts/inspector", "ops/inspector"]:
        for path in (root / base).rglob("*"):
            if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                selected[path.relative_to(root).as_posix()] = path
    for path in (root / "tests").glob("test_inspector*.py"):
        selected[path.relative_to(root).as_posix()] = path
    for name in ["RULES.md", "README.md", "HOSTED_LAUNCH.md"]:
        selected["docs/inspector/" + name] = root / "docs/inspector" / name
    selected["LICENSE"] = root / "docs/inspector/LICENSE"
    selected["pyproject.toml"] = root / "ops/inspector/pyproject.toml"
    credential = re.compile(rb"(?:[sr]k_(?:test|live)_|whsec_)[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}")
    for relative, source in selected.items():
        if ".private" in relative or relative.endswith(".env") or credential.search(source.read_bytes()):
            raise ValueError("private or credential-bearing payload refused")
        target = payload / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (payload / "README.md").write_text(PUBLIC_README)
    (payload / ".gitignore").write_text(".venv/\n.mcp-products/\n__pycache__/\n*.pyc\n*.egg-info/\n*.env\nbuild/\ndist/\n")
    files = sorted([*selected, "README.md", ".gitignore"])
    hashes = {name: hashlib.sha256((payload / name).read_bytes()).hexdigest() for name in files}
    manifest = {"repository": REPOSITORY, "files": hashes, "payload_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(), "private_files": 0}
    (folder / "payload-manifest.json").write_text(json.dumps(manifest, indent=2))
    if not args.apply:
        print(json.dumps({"prepared": True, "repository": REPOSITORY, "file_count": len(files), "payload_sha256": manifest["payload_sha256"]}, indent=2))
        return 0
    checkout = folder / "checkout"
    existing = subprocess.run(["gh", "repo", "view", REPOSITORY, "--json", "nameWithOwner"], capture_output=True, text=True, check=False)
    if existing.returncode:
        command(["gh", "repo", "create", REPOSITORY, "--public", "--description", "Local Python/FastAPI, Docker and Actions release evidence; optional private hosted report history."])
    if not (checkout / ".git").exists():
        command(["git", "clone", "https://github.com/" + REPOSITORY + ".git", str(checkout)])
    if command(["git", "-C", str(checkout), "remote", "get-url", "origin"]) != "https://github.com/" + REPOSITORY + ".git":
        raise ValueError("publication remote mismatch")
    if command(["git", "-C", str(checkout), "status", "--porcelain"]):
        raise ValueError("publication checkout has pending changes; preserve and inspect")
    for name in files:
        target = checkout / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(payload / name, target)
    command(["git", "-C", str(checkout), "add", "--", *files])
    changed = subprocess.run(["git", "-C", str(checkout), "diff", "--cached", "--quiet"], capture_output=True, check=False)
    if changed.returncode == 1:
        command(["git", "-C", str(checkout), "-c", "user.name=Content Sweep release", "-c", "user.email=release@contentsweep.ai", "commit", "-m", "Publish Inspector 0.3 local scanner and hosted report integration"])
    elif changed.returncode:
        raise ValueError("staged comparison failed")
    command(["git", "-C", str(checkout), "push", "origin", "HEAD"])
    head = command(["git", "-C", str(checkout), "rev-parse", "HEAD"])
    upstream = command(["git", "-C", str(checkout), "ls-remote", "origin", "HEAD"]).split()[0]
    if head != upstream:
        raise RuntimeError("remote publication not verified")
    command(["gh", "repo", "edit", REPOSITORY, "--homepage", "https://inspector.contentsweep.ai/inspector", "--add-topic", "fastapi", "--add-topic", "mcp", "--add-topic", "docker", "--add-topic", "github-actions"])
    exists = subprocess.run(["gh", "release", "view", "v0.3.0", "--repo", REPOSITORY], capture_output=True, check=False)
    if exists.returncode:
        notes = folder / "release-notes.txt"
        notes.write_text("Inspector 0.3: free local Python/FastAPI, Docker and Actions evidence, plus explicit hosted metadata submission. Hosted release reports: $19/100 with 3 free reports at https://inspector.contentsweep.ai/inspector. Linux/Python 3.12 qualified. Caller-submitted metadata is not independent source or runtime certification. Core scanning remains offline and Apache-2.0. See README for scope, privacy and installation.\n")
        command(["gh", "release", "create", "v0.3.0", "--repo", REPOSITORY, "--target", head, "--title", "Inspector 0.3.0", "--notes-file", str(notes), *[str(root / ".mcp-products/inspector/dist" / name) for name in ["contentsweep_prodcheck-0.3.0-py3-none-any.whl", "contentsweep_prodcheck-0.3.0.tar.gz", "manifest.json"]]])
    release = json.loads(command(["gh", "release", "view", "v0.3.0", "--repo", REPOSITORY, "--json", "url,assets"]))
    result = {"published": True, "repository_url": "https://github.com/" + REPOSITORY, "commit": head, "release_url": release["url"], "assets": [asset["name"] for asset in release["assets"]], "payload_sha256": manifest["payload_sha256"], "customer_contacts_sent": 0}
    (folder / "publication.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
