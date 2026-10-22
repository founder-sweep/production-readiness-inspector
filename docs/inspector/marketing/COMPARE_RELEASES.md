# Comparing release findings without uploading application source

Inspector compares finding instances across complete reports. An instance
includes a rule/version, relative path, semantic identity, and occurrence. This
lets a repeated finding stay unchanged when line numbers shift and keeps
duplicate occurrences separate. It is not proof of source-code lineage.

Start with the [agency quickstart](AGENCY_QUICKSTART.md) for the published
artifact, supported environment, and a runnable synthetic example.

## Keep a reviewed local baseline

On the first stable checkout, save a complete report and review its findings:

```bash
prodcheck /path/to/client-application --format json > reviewed-release.json
```

After the next release's changes, compare against that saved report:

```bash
prodcheck /path/to/client-application \
  --baseline reviewed-release.json --format json > next-release.json
```

The report records instance lists under `metadata.baseline`. For a CI policy
that gates only new instances, add `--new-only`; this still fails incomplete or
invalid evaluation. A baseline should be reviewed rather than automatically
replaced by an untrusted pull request.

| Comparison | Meaning |
|---|---|
| New | Present in the current complete report and absent from the baseline |
| Unchanged | Present in both reports with the same instance identity |
| Resolved | Absent from the current complete report under a comparable policy |

Line movement alone can preserve identity. Renames or substantive evidence
changes may create a new instance and resolve the old one. Inspector rejects
old rule-only, incomplete, or policy-incompatible baselines rather than silently
turning missing coverage into resolved findings.

## Preview what the hosted service will receive

```bash
python -m mcp_products.inspector.cloud preview next-release.json
```

The preview has rule/version/instance identities, relative paths and line
numbers, coverage, and input/scope fingerprints. It excludes raw source,
repository archives, excerpts, and arbitrary evidence prose. Review relative
names before submitting: a path can still reveal client or project information.

## Save comparable summaries under one project

Create a free workspace at [Inspector](https://inspector.contentsweep.ai/inspector#workspace)
and keep its key in a private file outside the scanned checkout. The cloud CLI
can also create a workspace and write a new private key file:

```bash
python -m mcp_products.inspector.cloud workspace --key-file /private/path/inspector-key
python -m mcp_products.inspector.cloud submit reviewed-release.json \
  --project client-api --key-file /private/path/inspector-key
python -m mcp_products.inspector.cloud submit next-release.json \
  --project client-api --key-file /private/path/inspector-key
python -m mcp_products.inspector.cloud history --key-file /private/path/inspector-key
```

Use a private directory you own and an initially nonexistent key file. Do not
commit, email, or paste the key into an issue. It is the only workspace
credential and has no email/password recovery.

Hosted history compares against the previous complete report saved for the same
project. The local baseline file is not uploaded as a separate baseline request.
A scope or ruleset change requires a new hosted project, so omitted inputs do
not appear fixed. Reports that have expired or been deleted cannot serve as
retained history. Keep reviewed local baselines and exports when longer history
is needed.

One new complete hosted report uses one credit. Exact retries reuse the prior
receipt without another debit. Invalid/incomplete summaries, incompatible
baselines, and service failures do not consume credits. The service retains
payloads for 30 days, with the maintenance/backup limits in its
[privacy terms](https://inspector.contentsweep.ai/inspector#terms).

## Review the result with the release owner

The [synthetic demonstration](assets/demonstration.json) starts with ten finding
instances and shows ten resolved instances after the supported configurations
change. Its HTML exports are real outputs from the hosted service in an internal
demonstration workspace. They are not customer results.

Download HTML from the browser's saved report list. The cloud CLI
`get --report-id REPORT_ID --key-file /private/path/inspector-key` returns the
JSON record. Review changes and coverage before writing the client
delivery note. The server preserves submitted static evidence and does not
independently inspect the source or verify runtime behavior.

Try **three hosted reports free**, then **$19 USD for 100**. Local scanning and
local baseline comparisons remain free; the paid pack adds hosted convenience
and export history without a subscription or automatic top-up.
