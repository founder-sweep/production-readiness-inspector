# A FastAPI client release handoff checklist

Use this checklist to give a client a record of the release you reviewed, the
static findings you addressed, and the runtime checks you performed separately.
Inspector supplies local static evidence and optional private report history.
The release owner still chooses and records the actual deployment checks.

## Before the scan

- Identify the client-approved checkout, commit or release tag, release owner,
  and intended environment. Keep the checkout stable while scanning.
- Review the files and ignore policy in scope. Keep repository permissions,
  client secrets, credentials, and unpublished source under your usual controls.
- Use the qualified Python 3.12/Linux environment and the reviewed Inspector
  artifact. See the [agency quickstart](AGENCY_QUICKSTART.md) for installation.
- Agree which findings block delivery. The default local CLI policy gates high
  findings. A failed or incomplete evaluation always needs attention.

## Review the static evidence

```bash
prodcheck /path/to/client-application --format json > release.json
```

- Check `metadata.complete`, `metadata.issues`, and coverage before interpreting
  the verdict. A partial evaluation cannot establish that old findings resolved.
- Review literal FastAPI debug and Uvicorn reload settings in supported inputs.
- Review directly declared GET health routes. Separately verify what those
  routes test in the running application.
- Review external Docker base digests, final explicit user, startup command
  form, and development reload findings. Inspect orchestration separately.
- Review external Actions references and permission declarations. Inspector's
  supported workflow parser is narrower than the full Actions/YAML language.
- For each relevant finding, record the fix, an accepted exception, or the
  reason it does not apply. A file/line finding is a review input.

## Verify the actual deployment separately

- Run the application's tests and the client's required acceptance checks.
- Verify environment-specific configuration and secret delivery without putting
  secret values into the report.
- Verify the deployed health behavior and any critical dependency checks.
- Confirm migration, rollout, rollback, logging, monitoring, and access decisions
  with the release owner where they apply.

Inspector does not execute those checks, import the application, resolve all
dynamic settings, or inspect every deployment technology. State the checks you
actually performed rather than using a static verdict as a runtime claim.

## Prepare the client handoff

- Preserve the reviewed local JSON report and the release/commit reference.
- For an existing baseline, run with `--baseline reviewed-release.json`. Review
  new, unchanged, and resolved finding instances along with current coverage.
- If using hosted history, preview the outgoing summary, use the same project
  name for comparable releases, and save only complete reports.
- Export the HTML handoff and record decisions outside the automated report.
  The export does not include the client's entire deployment review.
- Retain needed exports in the client's approved system before hosted payloads
  expire after 30 days. Keep the anonymous workspace key privately accessible
  to its authorized custodian; password/email recovery is unavailable.

## A compact delivery note

```text
Release / commit:
Review owner and date:
Inspector artifact / ruleset:
Static report complete and coverage reviewed:
New / unchanged / resolved instances:
Fixes and accepted exceptions:
Runtime checks actually performed:
Rollout and rollback owner:
Location of retained JSON / HTML exports:
```

See a [synthetic before-and-after handoff](AGENCY_QUICKSTART.md). Local scans
are free. [Hosted reports](https://inspector.contentsweep.ai/inspector#workspace)
include three free reports, then **$19 USD for 100**; there is no subscription
or automatic top-up.
