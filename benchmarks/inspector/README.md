# Inspector benchmark

Run from the canonical Git repository root, after building/installing the local
wheel in the product tools environment:

```bash
.mcp-products/inspector/tools/bin/python -m pip install --no-index --no-deps --force-reinstall \
  .mcp-products/inspector/dist/contentsweep_prodcheck-0.3.0-py3-none-any.whl
.mcp-products/inspector/tools/bin/python benchmarks/inspector/run.py
```

Output: `.mcp-products/inspector/benchmark/results.json`. No target code, remote
repositories or model/API calls are executed. Inputs: two composite static
fixtures and four generated microfixtures, labelled with exact expected finding
occurrence counts. Each CLI runs seven times. Inspector's stable report fields
must match across repetitions after removing only the observation timestamp.

The comparison script is a competent, ordinary AST + PyYAML safe-load + Docker
stage review for the common rules listed in `run.py`. It uses no Inspector
imports. It was authored by the same agent in the same implementation session,
so it is **not independent validation**. It trusts the fixture inputs and does
not implement Inspector's adversarial-input boundary, complete coverage report,
instance baselines, SARIF or transports. Do not use it on untrusted repositories.

Initial measurement, Python 3.12.3 / Ubuntu WSL2 x86_64, October 18, 2026:

| Scenario | Inspector median CLI ms | Script median CLI ms | Common-scope counts |
|---|---:|---:|---|
| Composite defect | 93.10 | 38.46 | Both match |
| Composite corrected | 92.38 | 38.53 | Both match |
| Comments/strings | 90.50 | 36.08 | Both match |
| Health name without route | 89.78 | 36.46 | Both match |
| Second application | 94.03 | 37.43 | Both match |
| Uvicorn alias | 95.06 | 37.57 | Both match |

Inspector starts an additional bounded worker. The latency comparison includes
process startup and uses tiny warm local fixtures; it is not a throughput/load
test. Exact numbers vary by machine/run. This demonstrates reproducibility and
fixture parity, not measured superiority, population precision/recall, customer
ROI, independent review or incident prevention. Baseline source hash is recorded
by the runner; changes require a new result packet. No public-repository holdout
or real customer data has been measured. Future useful evidence is blind review
of accepted/dismissed findings and actual integration/support time.
