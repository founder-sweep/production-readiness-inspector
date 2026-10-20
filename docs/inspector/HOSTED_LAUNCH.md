# Inspector hosted launch — October 20, 2026

The owner selected **$19 USD for 100 self-service release reports**, with the
local Apache-2.0 scanner remaining free. Version 0.3.0 adds an independent
metadata-only service. This supersedes the October 18 prepare-only commercial
packet; that historical packet does not describe current authorization.

## Offer and implementation

Customers create an anonymous workspace and save its API key. Three hosted
reports are free. A customer explicitly buys a 100-report pack through Stripe
Checkout; there is no subscription or automatic top-up. The key is the only
workspace credential and must be retained; there is no email/password recovery.

`prodcheck` keeps running locally without a network or account. The separate
browser preview / `python -m mcp_products.inspector.cloud preview report.json`
extracts only supported rule/version/instance identities, relative paths/lines,
coverage and fingerprints. Raw source, arbitrary evidence text, excerpts and
repository archives are excluded. An incomplete local report cannot be uploaded
as an accepted hosted report. Paths and fingerprints may still be sensitive;
customers review the outgoing summary before sending it.

Hosted value is private project history, new/unchanged/resolved instance
comparisons and HTML/JSON handoffs. The server does not rescan source or verify
the truth of a customer's submitted assertions. Reports expire after 30 days;
online maintenance removes expired payloads within one additional hour. Daily
product-owned backups are retained for up to seven days. Minimal financial and
idempotency receipts remain after payload deletion. A deleted/expired receipt
cannot silently consume a second credit on retry.

Each new valid hosted report uses one credit. Retries with the same key and
payload reuse the receipt. Invalid/incomplete submissions, policy-mismatched
baselines, provider failures and rejected requests do not consume credits. A
changed scope/ruleset needs a new project so omissions cannot appear resolved.
SQLite transactions serialize credit consumption. Cross-workspace access is
denied even when a report ID is known. HTML escapes user-supplied paths.

## Billing and separation

The existing Content Sweep LLC live account is reused. Inspector owns its
product/price, webhook signing secret, catalog namespace, workspace keys, SQLite
database, purchase receipts and credit ledger. There is no shared account,
wallet, database, worker, scheduler or marketing queue dependency. The existing
restricted runtime credential and verified business card-only configuration are
consumed as stable account configuration. The setup key stays on the operator's
machine and is never uploaded in service settings.

The catalog price is $19/100, one-time USD. The existing owner-reviewed cloud-only
no-collection tax configuration is recorded by reference; automatic tax is off
and no tax registration or shared business tax setting is changed. This records
configuration and an existing owner decision, not a new legal tax opinion.

Checkout grants nothing by itself. Signed payment notifications are verified,
the provider session and line items are retrieved fresh, and account mode,
owned price/offer, exact amount/currency/quantity, workspace/purchase, successful
payment intent and captured charge are checked before one 100-credit grant.
Unpaid/failed async sessions cannot grant credits. Refund events revoke the
corresponding credit fraction, with monotonic handling of out-of-order events.
Refunded consumed credit can hold future use; it never creates an automatic
charge. Internal qualification purchases retain their own immutable classification
and are excluded from independent revenue/adoption metrics.

## Operating envelope and deployment

Active: `https://inspector.contentsweep.ai/inspector`, a separate browser origin,
own container and own `/opt/contentsweep-inspector` storage on the existing host.
No new server, paid model, paid API, storage subscription or budget allocation
is authorized or needed. One small container receives bounded resources. The
portfolio's existing $200/month ceiling remains shared.

An additive DNS record and dedicated reverse-proxy virtual host are deployed.
The proxy configuration was validated and hot-reloaded. Existing container
identities, start times, restart counts and images remained unchanged. Local
shared root ops/source files are outside the write scope. The product deployment
script snapshots and validates the exact additive remote integration and retains
rollback material. Service keys, private manifests and runtime data stay ignored.

Body size is bounded at 2 MB; findings at 2,000; path length at 512 bytes. Signup,
checkout and submissions are rate-limited. There is a 256 MiB active database
admission ceiling and no high-availability/SLA claim. A beta capacity problem
blocks new purchases/submissions rather than auto-provisioning paid resources.
Daily SQLite backup/restore and stored metadata retention are product-owned.

## Qualification and actual outcomes

On October 20 the public HTTPS service passed workspace creation, three-credit
trial accounting, report submission, exact retry without a second debit,
instance-level baseline comparison, cross-workspace denial, invalid-input
rejection without debit, HTML export and direct wheel download. TLS validation
passed. Billing is enabled. The deployed wheel SHA-256 is
`9761f945a9b6d618ea7f16a381036992803522c038501b303a2cbe334da36b71`.

The live provider catalog and a Checkout created through the public HTTPS API
were verified at exactly $19 USD for 100 reports with the owned one-time price
and card-only configuration. Retrying returned the same Checkout. It was expired
unpaid; the workspace balance stayed unchanged and no live charge was created.

An actual Stripe sandbox Checkout completed, and an actual full sandbox refund
succeeded. Fresh provider reads exercised the same fulfillment engine, granting
100 credits once and revoking 100 on refund. The public test observer received
and verified a real signed provider notification while leaving the live ledger
untouched. These are separate sandbox fulfillment and signed-delivery checks;
they are not a claim of an end-to-end paid live transaction. Production webhook
signature, ownership, amount/mode and idempotency behavior also have automated
regression coverage.

After activation, HTTPS checks passed again. A backup of the deployed SQLite
database restored into a separate product-owned file, passed `integrity_check`
and retained all checked rows without modifying the active database. Product
container replacement preserved the stored trial reports and receipts.

The repository qualification suite passed 313 tests, including 74 Inspector
tests; Ruff, compilation and dependency checks passed. The shared qualifier's
secret scan could not invoke unavailable `rg`; the product-owned Python
equivalent passed separately. The shared local smoke has an unrelated Schema
Mapper CLI contract failure; Inspector's own CLI, loopback HTTP and official-SDK
MCP smoke passed. Shell checks and an Opera screenshot of the live page are
distinct evidence; no native Windows GUI readiness claim is made.

At activation there were **zero independent paid purchases and $0 independent
gross revenue**. Qualification workspaces/purchases are internally classified
and excluded from revenue/adoption metrics. The chosen offer does not authorize
an owner-funded live charge. Private keys, session URLs and raw operator proofs
remain in ignored product-owned storage.

## Public distribution and demand

Publish only Inspector-owned Apache source, tests, synthetic fixtures, download
artifacts and supported-stack docs. Keep the free local CLI useful. The paid
call to action links to the actual $19/100 workspace checkout. GitHub/PyPI/registry
acceptance must be verified independently; do not invent a published package
or claim an independent buyer from internal qualification.

No prospect emailing, direct messaging or paid promotion is authorized by a
general launch request. Prepared interview/outreach copy remains unsent until
specific recipient/content authorization. Organic public distribution and the
live product page are the initial acquisition surface. Record actual independent
paid purchases, refunds, repeat use, support time and attributable discovery.
