"""Self-contained product UI. Third-party scripts and source uploads are absent."""
import html

CSS = """
:root{color-scheme:light;--ink:#142c34;--muted:#536c73;--paper:#f5f6ef;--line:#d7dfd7;--accent:#205c45}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.6 system-ui,sans-serif}header,main,footer{max-width:1120px;margin:auto;padding:24px}header{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line)}a{color:var(--accent)}nav a{margin-left:20px}h1{font-size:clamp(40px,6vw,72px);line-height:1.08;max-width:830px;letter-spacing:-.045em}h2{font-size:30px;line-height:1.2}h3{font-size:20px}p{max-width:760px}.eyebrow{color:var(--accent);font-size:13px;font-weight:800;letter-spacing:.13em;text-transform:uppercase}.lead{font-size:21px;color:var(--muted)}.hero{padding:48px 0 36px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:26px}button,.button{display:inline-block;background:var(--accent);border:0;color:white;padding:12px 20px;border-radius:7px;font:600 16px system-ui;cursor:pointer;text-decoration:none}button:disabled{opacity:.45;cursor:wait}button.secondary{background:#e6eee8;color:var(--ink)}label{display:block;margin:14px 0 6px}input{font:inherit;padding:10px;border:1px solid #aebeb5;border-radius:6px;max-width:100%;width:100%}input[type=file]{background:white}.small{font-size:14px;color:var(--muted)}.price{font-size:42px;font-weight:750;margin:4px 0}code,pre{font:14px/1.5 ui-monospace,monospace;word-break:break-all}pre{white-space:pre-wrap;background:#edf2eb;padding:15px;border-radius:6px;max-height:440px;overflow:auto}section{scroll-margin-top:20px;margin:30px 0 45px}.notice{border-left:4px solid var(--accent);padding:12px 18px;background:#e6eee8}#status{padding:12px 0;min-height:45px}li{margin:8px 0}#history button{padding:6px 12px;margin-left:12px}footer{border-top:1px solid var(--line);font-size:14px;color:var(--muted)}.row{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.hidden{display:none}details{margin:12px 0}summary{cursor:pointer;font-weight:650}@media(max-width:600px){header,main,footer{padding:18px}nav a{margin-left:10px}h1{font-size:43px}.hero{padding-top:26px}.card{padding:20px}}
"""


def landing(enabled: bool, mode: str, support_email: str = ""):
    payment = "Buy 100 reports · $19" if enabled else "Checkout is being qualified"
    state = "Live checkout" if enabled and mode == "live" else "Test environment · no live purchase" if mode == "test" else "Free reports available · paid checkout pending"
    contact = ('<a href="mailto:' + html.escape(support_email, quote=True) + '">' + html.escape(support_email) + '</a>') if support_email else 'the merchant contact at <a href="https://contentsweep.ai">Content Sweep</a>'
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Inspector — evidence before your next Python release</title><meta name="description" content="Scan Python/FastAPI, Docker and Actions locally. Save private release reports, compare baseline changes and export a handoff. $19 for 100 hosted reports."><link rel="stylesheet" href="/inspector/style.css"><script src="/inspector/app.js" defer></script></head><body>
<header><strong>◈ Inspector</strong><nav><a href="#how">How it works</a><a href="#pricing">Pricing</a><a href="#workspace">Workspace</a></nav></header><main>
<section class="hero"><div class="eyebrow">For Python builders and agent-driven teams</div><h1>Leave evidence with your next release.</h1><p class="lead">Scan FastAPI, Docker and GitHub Actions locally. Keep a private report history, see what changed, and download a clear handoff.</p><div class="row"><a class="button" href="#workspace">Try 3 hosted reports free</a><a href="/inspector/download/contentsweep_prodcheck-0.3.0-py3-none-any.whl">Download the free local CLI</a></div><p class="small">No application-source upload. No subscription. Local scanning stays free under Apache-2.0.</p></section>
<section id="how"><div class="grid"><article class="card"><div class="eyebrow">01 · Scan locally</div><h3>Your code stays on your machine.</h3><p>Run the bounded static scanner. Review its file evidence, errors and coverage before proceeding.</p><pre>prodcheck . --format json &gt; report.json</pre></article><article class="card"><div class="eyebrow">02 · Preview metadata</div><h3>Send a report, not a repository.</h3><p>Preview relative paths, line numbers, rule IDs, coverage and opaque fingerprints. Raw source, excerpts and arbitrary facts are excluded.</p></article><article class="card"><div class="eyebrow">03 · Keep the handoff</div><h3>Track fixes across releases.</h3><p>Each hosted report compares against the previous complete report for that project. Download HTML/JSON and keep a 30-day private history.</p></article></div></section>
<section><h2>Know the scope before trusting the verdict.</h2><p>Inspector checks literal FastAPI/Uvicorn settings, directly declared conventional GET health routes, final Docker startup configuration and supported Actions declarations. It reports syntax and bounded inference.</p><p class="notice">A health route declaration does not prove runtime readiness. Dynamic configuration and unsupported syntax may return incomplete analysis. This is not a vulnerability scanner or production certification. Hosted reports preserve caller-submitted evidence; they do not independently rescan or verify your source.</p><details><summary>Supported stack and coverage</summary><p>Qualified on Python 3.12/Linux and Ubuntu WSL2. Docker ordinary syntax and a documented YAML subset are supported. Cross-file router resolution, Compose/Kubernetes, general secret detection, CVEs and runtime tests are outside this beta. See the source archive for the full rule contract and limits.</p></details></section>
<section id="pricing"><h2>A simple pack for release history.</h2><div class="grid"><article class="card"><div class="eyebrow">Local CLI</div><div class="price">Free</div><p>Offline static checks, file evidence, JSON/text/SARIF, local baselines and stdio MCP. No account or hosted payment required.</p><a href="/inspector/download/contentsweep_prodcheck-0.3.0.tar.gz">Source, tests and integration examples</a></article><article class="card"><div class="eyebrow">Hosted reports</div><div class="price">$19 <span class="small">USD / 100 reports</span></div><p>Private projects, complete report history for 30 days, instance-level change comparisons and downloadable HTML/JSON handoffs.</p><p>One new complete hosted report uses one credit. Exact retries are free. Invalid/incomplete summaries and service failures do not consume credits. Credits do not expire; no automatic top-up.</p><p class="small">STATUS_LABEL</p><a class="button" href="#workspace">Start with 3 free reports</a></article></div></section>
<section id="workspace"><h2>Your private workspace</h2><p>Create a workspace for three free reports. Save the API key: it is the only way to access this workspace, including purchases. We do not collect a sign-in email or provide password recovery.</p><div class="card"><div class="row"><button id="create">Create free workspace</button><button id="restore" class="secondary">Use saved key</button></div><label for="key">Workspace API key</label><input id="key" type="password" autocomplete="off" spellcheck="false" placeholder="Paste your saved key"><div class="row"><button id="save" class="secondary">Connect key</button><button id="show" class="secondary">Show / hide key</button></div><p class="small">This browser stores the key only after you connect. Avoid a shared browser. Keep a private copy before purchasing.</p><p id="balance">Connect a workspace to see your balance.</p><button id="buy" disabled>PAYMENT_LABEL</button><p class="small">Stripe-hosted checkout. A completed payment grants 100 credits after verified fulfillment. The return page never grants credits.</p><hr><label for="project">Project name</label><input id="project" value="my-service" maxlength="64"><label for="file">Complete Inspector report.json</label><input id="file" type="file" accept="application/json,.json"><p class="small">The file is parsed in your browser. Only the previewed structured summary is sent. Relative paths can contain sensitive names; review them first.</p><pre id="preview">Select a complete local Inspector JSON report to preview the outgoing summary.</pre><button id="submit" disabled>Save report · 1 credit</button><p id="status" role="status" aria-live="polite"></p><h3>Saved reports</h3><ul id="history"></ul></div></section>
<section><h2>Use it in CI or a coding-agent handoff.</h2><pre>export INSPECTOR_API_KEY=your_private_workspace_key
python -m mcp_products.inspector.cloud preview report.json
python -m mcp_products.inspector.cloud submit report.json --project my-service</pre><p>Inspect the preview before using the network command. Configure trusted artifacts and a reviewed local scan policy. Local-only use has no network dependency.</p></section>
<section id="terms"><h2>Beta terms, privacy and refunds</h2><details><summary>What is stored, and for how long?</summary><p>Only the submitted structured summary, relative paths/lines, coverage, fingerprints, project names and comparisons are stored with your workspace. No source archives, raw code, arbitrary evidence text or model processing is accepted. Reports expire after 30 days and active-service maintenance removes expired payloads within an additional hour. Idempotency/payment receipts and credit accounting are retained. Operational backups may retain deleted report payloads for up to seven additional days. You can delete a report payload using the API.</p></details><details><summary>Purchases, refunds and key safety</summary><p>Content Sweep LLC sells prepaid hosted report credits at $19 USD for 100. There is no subscription or automatic charge. Request a refund of unused purchased credits within 14 days through the merchant contact on your Stripe receipt. Refunds revoke corresponding credits; consumed refunded credits can block future submissions without creating an automatic charge. Save your key before buying; a lost anonymous key cannot be recovered from a password or email account. This beta has no contractual uptime guarantee.</p></details><details><summary>Free software, support and limits</summary><p>The local scanner is Apache-2.0 software and stays usable without this service. Hosted history/comparisons are the paid convenience. A receipt or hosted report is not independent source verification, a security guarantee or certification. For billing/support use the Content Sweep LLC contact shown by Stripe checkout/receipts. Data exports and private API integration are included in the source release.</p></details></section>
</main><footer>Content Sweep LLC · Inspector beta · Local evidence, private release history · <a href="/inspector/download/manifest.json">Release hashes</a> · <a href="#terms">Terms and privacy</a> · Support: CONTACT_LABEL</footer></body></html>""".replace("PAYMENT_LABEL", payment).replace("STATUS_LABEL", state).replace("CONTACT_LABEL", contact).replace("through the merchant contact on your Stripe receipt", "through CONTACT_LABEL".replace("CONTACT_LABEL", contact)).replace("For billing/support use the Content Sweep LLC contact shown by Stripe checkout/receipts.", "For billing/support contact " + contact + ".")


JAVASCRIPT = r"""
'use strict';
const $ = id => document.getElementById(id);
let key = localStorage.getItem('inspector-key') || '';
let summary = null;
let checkoutIntent = null;
$('key').value = key;
function status(text) {$('status').textContent = text;}
async function api(path, method='GET', body=null) {
  const headers = {'Authorization': 'Bearer '+key};
  if (body !== null) headers['Content-Type']='application/json';
  const response = await fetch('/inspector/api/'+path, {method, headers, body:body===null?null:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'request_failed');
  return data;
}
async function refresh() {
  if(!key) return;
  const data=await api('balance');
  $('balance').textContent=data.reports_remaining+' hosted report credits remaining'+(data.revoked_credit_debt?' · refunded-credit hold: '+data.revoked_credit_debt:'');
  const health=await (await fetch('/inspector/health')).json();
  $('buy').disabled=!health.billing_enabled;
  const history=await api('reports');
  $('history').replaceChildren();
  for(const report of history.reports) {
    const item=document.createElement('li');
    item.textContent=report.project+' · '+new Date(report.created*1000).toLocaleString();
    const button=document.createElement('button');button.textContent='Download HTML';
    button.addEventListener('click', async()=>{
      try {
        const response=await fetch('/inspector/api/reports/'+encodeURIComponent(report.id)+'/html',{headers:{Authorization:'Bearer '+key}});
        if(!response.ok) throw new Error('report_expired_or_unavailable');
        const blob=await response.blob(), link=document.createElement('a'), url=URL.createObjectURL(blob);
        link.href=url;link.download=report.id+'.html';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      } catch(error) {status(error.message);}
    });
    item.append(button);$('history').append(item);
  }
}
async function connect() {key=$('key').value.trim();await refresh();localStorage.setItem('inspector-key',key);status('Connected. Keep a private copy of this key.');}
$('create').addEventListener('click',async()=>{
  try {
    if(key && !window.confirm('A workspace key is already loaded. Create another workspace? Keep the existing key first.')) return;
    const response=await fetch('/inspector/api/workspaces',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const data=await response.json();if(!response.ok) throw new Error(data.error);
    $('key').value=data.api_key;key=data.api_key;await connect();status('Workspace created. Save your key privately before purchasing.');
  } catch(error) {status(error.message);}
});
$('save').addEventListener('click',()=>connect().catch(error=>status(error.message)));
$('restore').addEventListener('click',()=>{$('key').focus();status('Paste your saved API key, then connect.');});
$('show').addEventListener('click',()=>{$('key').type=$('key').type==='password'?'text':'password';});
$('buy').addEventListener('click',async()=>{
  try {
    if(!key) throw new Error('Connect and save your workspace key first.');
    checkoutIntent=checkoutIntent||crypto.randomUUID();$('buy').disabled=true;
    const data=await api('checkout','POST',{idempotency_key:checkoutIntent});
    const url=new URL(data.url);if(!['https://checkout.stripe.com','https://checkout.contentsweep.ai'].includes(url.origin)) throw new Error('Invalid checkout response');
    location.assign(data.url);
  } catch(error) {status(error.message);$('buy').disabled=false;}
});
$('file').addEventListener('change',async()=>{
  summary=null;$('submit').disabled=true;
  try {
    const file=$('file').files[0];if(!file) return;if(file.size>8000000) throw new Error('Report file exceeds 8 MB.');
    const report=JSON.parse(await file.text()), metadata=report.metadata;
    if(report.product!=='production-readiness-inspector'||!metadata||metadata.complete!==true||(metadata.issues||[]).length) throw new Error('Select a complete local Inspector report.');
    summary={schema_version:'inspector-summary-v1',product:report.product,profile:metadata.profile,ruleset_version:metadata.ruleset_version,input_fingerprint:report.input_fingerprint,scope_fingerprint:metadata.scope_fingerprint,coverage:report.coverage,findings:report.findings.map(item=>({rule_id:item.id,rule_version:item.metadata.rule_version,instance_id:item.metadata.instance_id,path:item.metadata.path,line:item.metadata.line}))};
    $('preview').textContent=JSON.stringify(summary,null,2);$('submit').disabled=false;status('Preview ready. Only this summary will be sent.');
  } catch(error) {status(error.message);}
});
$('submit').addEventListener('click',async()=>{
  try {
    if(!summary||!key) throw new Error('Connect a workspace and preview a complete report.');
    $('submit').disabled=true;
    const project=$('project').value.trim(), encoded=new TextEncoder().encode(JSON.stringify([project,summary]));
    const hash=await crypto.subtle.digest('SHA-256',encoded), id=Array.from(new Uint8Array(hash)).map(x=>x.toString(16).padStart(2,'0')).join('');
    const data=await api('reports','POST',{project,summary,idempotency_key:id});
    status((data.duplicate?'Existing receipt reused; no new credit consumed.':'Report saved; one credit used.')+' New '+data.comparison.new.length+', resolved '+data.comparison.resolved.length+'.');
    await refresh();
  } catch(error) {status(error.message);} finally {$('submit').disabled=!summary;}
});
if(key) refresh().catch(error=>status(error.message));
if(new URLSearchParams(location.search).get('checkout')==='complete') {
  status('Checkout returned. Credits appear after verified payment fulfillment.');
  for(let i=1;i<=6;i++) setTimeout(()=>refresh().catch(error=>status(error.message)),i*3000);
}
"""
