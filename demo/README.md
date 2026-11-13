# Show ten resolved findings in a FastAPI release handoff

Inspect the owned defective and corrected fixtures locally, compare their reports and refuse a path outside the chosen root.

Owned synthetic example. Recorded results are clearly separated from live execution. Installing a skill does not install its runtime or authorize spending or uploads.

## Inspect the evidence

Read `manifest.json`, `expected.json`, and the fixtures before running. The walkthrough covers defective, corrected, root-escape. Results come from actual product MCP calls, not simulated responses. The free public page and downloads require no sign-in.

## Reproduce with your agent

Read the existing `inspect-release` skill and its companion setup/tool references. Then follow `AGENT_PROMPT.md`. On macOS, install the reviewed Inspector source with its MCP extra in a dedicated Python 3.12+ environment. The immutable 0.3.0 wheel retains its Linux qualification. Use the installed prodcheck-mcp executable absolute path.

These commands are qualified on macOS and Linux. Follow [client setup](https://github.com/founder-sweep/production-readiness-inspector/blob/main/CLIENTS.md) for runtime installation. Use that environment’s Python to run the demo.

For deterministic verification from this repository root:

```sh
python demo/run.py --mode local --command /ABSOLUTE/TO/ENV/bin/prodcheck-mcp --output demo-results
```

This local demo requires no hosted evaluation allowance or API key. Review the supplied field decisions before approving them. It grants no permission for customer files, purchases, destination writes, source edits or cloud actions. Hosted keys are your own; local analysis needs no hosted key.

Reuse the same output directory and allowance after an uncertain response. `resume.private.json` preserves quote/key/job identities before dispatch. Keep it private. Never start a new run merely because polling timed out. Changed customer data needs its own review and authorization. A completed rejection, block or warning can be billable as documented for this product.

## Interpret the result

Inspect `result.json` for assertions, complete reports and actual tool discovery. Expected stop cases are part of a passing demo. A deterministic runner is not a native agent completion. Machine-generated IDs, timestamps and local paths may differ; business values, coverage and accounting must agree.

Static local Python/FastAPI, Docker and GitHub Actions inspection. No target-code execution or source upload. Python 3.12+; reviewed source installation on macOS, qualified 0.3.0 wheel on Linux.

## Price and next step

Local CLI and MCP are free. Optional hosted metadata reports have three trials, then $19/100 reports.

[Read the full walkthrough and setup](https://inspector.contentsweep.ai/inspector/demos/release-handoff) · [Product and current terms](https://inspector.contentsweep.ai/)

Keep local/free options separate from optional hosted purchases. This example performs no purchase. Reports are bounded evidence, not runtime certification or proof of customer outcomes.

<!-- demo-specific-walkthrough -->
## Read the handoff

Open the [recorded release handoff](https://inspector.contentsweep.ai/inspector/demos/release-handoff/handoff.html). It lists the ten actual findings with file evidence; the corrected fixture has zero and the baseline comparison resolves all ten. The authorized root contains only the supplied fixtures. A request outside it returns incomplete coverage and refusal; target code is never executed or uploaded.
