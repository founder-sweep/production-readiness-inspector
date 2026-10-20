# Production Readiness Inspector beta

Hosted release reports and baseline history are now implemented separately from
the free local scanner. The owner selected $19 USD for 100 hosted reports. See
[the current hosted launch record](HOSTED_LAUNCH.md) for activation evidence,
customer privacy, payment accounting and operating limits.


`prodcheck` returns file/line evidence for static operability checks in local
Python/FastAPI applications, Dockerfiles and GitHub Actions workflows. It runs
offline, does not import the application or execute its tests/builds, and needs
no account. Apache-2.0. Version 0.3.0; ruleset `2026.10.18.1`.

## Install and run

Qualified platform: Python 3.12 on Linux/Ubuntu WSL2. Native Windows/macOS are
not qualified. The core uses only the Python standard library. Use a dedicated
environment for the standalone wheel; do not install the standalone distribution
over an existing `mcp-products` suite environment (they own the same Inspector
namespace). The wheel is distributed directly over HTTPS and through GitHub
releases. No PyPI or MCP registry acceptance is claimed.

From the canonical checkout, existing users can run without reinstalling:

```bash
cd "$(git rev-parse --show-toplevel)"
.venv/bin/python -m mcp_products.inspector examples/inspector/defective --format json
.venv/bin/prodcheck examples/inspector/corrected --format text
```

Build a standalone wheel and source archive, using only product-owned tools:

```bash
python3 -m venv .mcp-products/inspector/tools
.mcp-products/inspector/tools/bin/python -m pip install -r ops/inspector/requirements-tools.txt
.mcp-products/inspector/tools/bin/python scripts/inspector/build_release.py
python3 -m venv .mcp-products/inspector/install-check
.mcp-products/inspector/install-check/bin/python -m pip install --no-index --no-deps \
  .mcp-products/inspector/dist/contentsweep_prodcheck-0.3.0-py3-none-any.whl
.mcp-products/inspector/install-check/bin/prodcheck examples/inspector/corrected
```

The synthetic corrected Docker digest and action SHA are parsing fixtures, not
downloadable images/actions. Do not build/run those fixtures. The scanner/CI
reference integration itself is runnable; no fixture code execution is needed.

## Results and CI policy

`--format text|json|sarif` uses one engine. Preserve the JSON report to compare
instances on a later run. A complete scan means this profile's selected inputs
and rules were evaluated, not that the entire repository or deployment is safe.

| Outcome | Meaning | Exit |
|---|---|---:|
| `ready` | No finding in shipped rules; inspect coverage | 0 |
| `needs_review` | Findings exist; policy threshold controls the exit | 0 or 2 |
| `error` / `incomplete` | Missing input, parse/evaluation/budget error or unresolved supported configuration | 5 |
| Invalid CLI syntax | argparse usage error | 2 |

The default threshold is **high**. `--fail-on medium` also gates advisory medium
findings. `--fail-on critical` permits current findings, since this rule pack
has no critical rule. `--fail-on none` reports findings without gating them.
Every threshold still returns 5 for failed/incomplete evaluation. Earlier CLI
versions returned 2 only for blocking verdicts; high findings now gate by default.

```bash
prodcheck PATH --format json > report.json
# Exit 2 is an analysis outcome, not a crash. Review before adopting a baseline.
prodcheck PATH --baseline reviewed-report.json --new-only --format json
prodcheck PATH --format sarif > report.sarif
```

Baselines require a complete report with this ruleset, instance format and scope
policy. An empty, malformed, old rule-ID-only or differently ignored/budgeted
baseline fails explicitly. Findings have rule/version and an opaque instance
identity based on path, semantic evidence and duplicate occurrence. Line shifts
preserve identity; renames or substantive evidence edits create new instances.
Identical duplicates are a multiset, not proof of source-code lineage. Partial
scans never declare old instances resolved. `--new-only` requires `--baseline`.
Baselines are a caller-reviewed artifact, not authenticated attestation.

## Supported inputs and limits

- Direct `.py` files; recognized `fastapi.FastAPI`/`APIRouter` and `uvicorn.run`
  imports, aliases, lexical bindings, literal debug/reload and direct route
  declarations. Included routers, dynamic settings, star imports and runtime
  routing are not resolved. Only `/health`, `/healthz`, `/ready`, `/readyz` with
  GET count as conventional. A function name alone does not count. Registered
  routes do not prove dependency health, liveness or readiness behavior.
- `Dockerfile`, `Dockerfile.*`, `Containerfile`, `Containerfile.*`: ordinary
  instructions, continuations, internal stages, explicit final/inherited USER,
  final CMD/ENTRYPOINT shell form and Uvicorn reload. External image defaults,
  build targets, variable expansion, shell scripts and runtime orchestration
  are not evaluated. Heredocs and non-backslash escape directives fail clearly.
- `.github/workflows/*.yml|yaml` under an analysis directory: a constrained YAML
  subset with mappings, sequences, quoted/plain scalars, flow collections and
  opaque block strings. Anchors, tags, merges, duplicate keys, multiline quoted
  or flow values and multiple documents are rejected. This is not full YAML or
  Actions schema validation. Local actions are exempt from external pinning;
  remote actions/reusable workflows need a full SHA; docker actions need a digest.
- A nonignored `.env`/`.env.*` is presence-only evidence, including nested files;
  example/sample/template names are exempt. Values are never read or hashed.
  Presence is not proof of committed credentials. No general secret detector is
  advertised. Source snippets and parser messages are never returned.

The scanner reads nested `.gitignore` and `.prodcheckignore` (later patterns
override earlier ones). Supports comments, basename/glob patterns, slash-relative
patterns, directory patterns, `**` and `!` negation. Excluded directories are
pruned; negation cannot restore their children without restoring the parent.
Escaped patterns, excessive pattern length/depth/count and unsupported encoding
fail evaluation. Global Git ignores and `.git/info/exclude` are not consulted;
ignore patterns apply even to tracked files. This is a scan policy, not a Git
index inspection. Report scope changes require baseline review.

Private/generated directories and hidden files/directories are excluded, except
`.github`, ignore files and environment presence checks. Default exclusions:
`.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `.mypy_cache`,
`.pytest_cache`, `.mcp-products`, `secrets`, `backups`, `runtime`.
Symlinks are never followed; roots with any symlink ancestor fail. Relevant file
symlinks produce an evaluation issue; directory symlinks are excluded and counted.
FIFOs/devices are not read. Hard links and mount boundaries are not a tenant
isolation mechanism; this beta is for files the local operator authorizes.

Defaults: 1 MB/file, 16 MB read total, 2,000 relevant files, 20,000 directory
entries, 2,000 findings, depth 32; 10 seconds cooperative budget plus a hard
12-second child lifetime. Linux child address space 512 MiB, CPU 11 seconds,
128 descriptors. Limits are configurable programmatically within fixed ceilings.
Exceeded/failed evaluation never returns ready. Fingerprints cover consumed
supported bytes, ignore files and environment presence, not excluded files or
an atomic repository snapshot. Use a stable checkout for release evidence;
mtime/size changes during individual reads are detected, but arbitrary concurrent
multi-file changes cannot be proven absent. Hashes are not anonymization.

## Programmatic, MCP and local HTTP

```python
from mcp_products.inspector import Limits, inspect_repository
from mcp_products.inspector.reporting import exit_code

result = inspect_repository("PATH", limits=Limits(max_seconds=10))
print(result.to_dict())
raise SystemExit(exit_code(result, fail_on="high"))
```

The Inspector-only stdio MCP adapter uses official SDK 2.3.0. In a standalone
environment install its optional dependency with `python -m pip install
'mcp==2.3.0'`, then run:

```bash
python -m mcp_products.inspector.mcp --root APPROVED_LOCAL_DIRECTORY
```

It exposes only `inspect_repository(path=".", baseline=None)`, with typed inputs
and read-only/closed-world annotations. Paths are relative to the configured root.
The existing suite MCP registration remains available, but its tool set is shared;
use this product-only adapter for independent integration.

For a local HTTP client, create a random ASCII token (32+ characters), pass it via
`INSPECTOR_TOKEN`, and run:

```bash
python -m mcp_products.inspector.api --root APPROVED_LOCAL_DIRECTORY --port 18182
# POST http://127.0.0.1:18182/v1/inspect
# Authorization: Bearer <token>, Content-Type: application/json
# Body: {"path":"."}
```

HTTP binds only loopback, requires the bearer token, checks Host, rejects browser
Origin requests, limits request bodies to 16 KiB and handles one scan at a time.
HTTP 200 means a complete report (including findings); 422 means failed/incomplete
analysis; 400/401/403/413 cover invalid requests/auth/origin/size. HTTP has no
baseline upload interface. Tokens/bodies/source are not logged or retained.
Reports stay in memory until returned; the caller controls any saved files.
Do not reverse proxy this into a customer service. This local adapter has no upload/archive ingestion, remote repository URL,
tenant authentication or billing. The separate hosted service accepts only
structured report summaries and uses its own workspace authentication/accounting.

## Verification and integration

Use [the reference integration](../../integrations/inspector/README.md),
[rules and sources](RULES.md),
[benchmark method](../../benchmarks/inspector/README.md) and
[the hosted launch record](HOSTED_LAUNCH.md).

```bash
.venv/bin/python -m pytest tests/test_inspector_engine.py tests/test_inspector_interfaces.py tests/test_inspector_commerce.py
.venv/bin/python scripts/inspector/smoke.py
.venv/bin/python scripts/inspector/secret_scan.py
```

The standalone test environment needs the `hosted,mcp` extras, pytest and httpx;
see the root README. In the original MCPProducts suite, `bash scripts/qualify.sh`
and `python scripts/smoke-local.py` are additional shared checks. Its qualifier's
missing-`rg` branch does not run its credential scan. The last command above is
an equivalent over Git-tracked/nonignored files and prints only filenames/counts.
It is a narrow credential-pattern check, not a guarantee that every kind of
secret is absent. No shared service restart is required.
