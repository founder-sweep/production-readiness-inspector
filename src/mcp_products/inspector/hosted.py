"""Public metadata-only report service; never accepts repositories or runs scans."""
from __future__ import annotations

import asyncio
import hashlib
import html
import ipaddress
import json
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from .billing import Billing, HostedSettings, StripeGateway
from .commerce import AMOUNT, CREDITS, CommerceError, ReportStore
from .model import RULES
from .web import CSS, JAVASCRIPT, landing

PREFIX = "/inspector"


def render_report(report):
    summary = report.get("summary")
    if summary is None:
        raise CommerceError("report_expired_or_deleted", 410)
    rows = []
    comparison = report["comparison"]
    for finding in summary["findings"]:
        _, severity, title, remediation = RULES[finding["rule_id"]]
        state = "new" if finding["instance_id"] in comparison["new"] else "unchanged"
        values = [finding["rule_id"], severity, title, f"{finding['path']}:{finding['line']}", state, remediation]
        rows.append("<tr>" + "".join("<td>" + html.escape(value) + "</td>" for value in values) + "</tr>")
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Inspector release report</title><h1>Inspector release report</h1><p>Project: {}</p>
<p>Caller-submitted static evidence. Source and runtime behavior were not independently verified.</p>
<p>Ruleset: {} · New: {} · Unchanged: {} · Resolved: {}</p>
<p>Input: {}</p><table><thead><tr><th>Rule</th><th>Severity</th><th>Finding</th><th>Location</th><th>Change</th><th>Remediation</th></tr></thead><tbody>{}</tbody></table>
<h2>Coverage</h2><pre>{}</pre><p>A clean static report is not deployment certification.</p></html>""".format(html.escape(report["project"]), html.escape(summary["ruleset_version"]), len(comparison["new"]), len(comparison["unchanged"]), len(comparison["resolved"]), html.escape(summary["input_fingerprint"]), "".join(rows), html.escape(json.dumps(summary["coverage"], indent=2)))


def create_app(settings: HostedSettings | None = None, *, gateway=None):
    settings = settings or HostedSettings.from_environment()
    store = ReportStore(settings.database, settings.mode)
    if gateway is None and settings.stripe_key:
        gateway = StripeGateway(settings)
    billing = Billing(settings, store, gateway)

    @asynccontextmanager
    async def lifespan(_app):
        async def maintenance():
            while True:
                await run_in_threadpool(store.maintain)
                await asyncio.sleep(3600)
        task = asyncio.create_task(maintenance())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="Inspector reports", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store, app.state.settings = store, settings
    origin = urlparse(settings.base_url).scheme + "://" + urlparse(settings.base_url).netloc
    host = urlparse(settings.base_url).netloc

    def ip_bucket(request):
        peer = request.client.host if request.client else "unknown"
        if settings.proxy_network:
            try:
                if ipaddress.ip_address(peer) in ipaddress.ip_network(settings.proxy_network):
                    peer = str(ipaddress.ip_address(request.headers.get("X-Inspector-Client-IP", peer)))
            except ValueError:
                pass
        return hashlib.sha256((str(settings.database) + peer).encode()).hexdigest()

    def auth(request):
        value = request.headers.get("Authorization", "")
        return store.authenticate(value.removeprefix("Bearer ") if value.startswith("Bearer ") else "")

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        try:
            if request.headers.get("host") != host:
                raise CommerceError("host_rejected", 403)
            if request.headers.get("origin") not in {None, origin}:
                raise CommerceError("origin_rejected", 403)
            if request.method in {"POST", "DELETE"}:
                length = request.headers.get("content-length")
                if length and (not length.isdecimal() or int(length) > 2_000_000):
                    raise CommerceError("request_size_limit", 413)
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise CommerceError("request_size_limit", 413)
                request._body = bytes(body)
            response = await call_next(request)
        except CommerceError as exc:
            response = JSONResponse({"error": exc.code}, status_code=exc.status)
        response.headers.update({
            "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self' https://checkout.stripe.com https://checkout.contentsweep.ai",
        })
        return response

    @app.exception_handler(CommerceError)
    async def business_error(_request, exc):
        return JSONResponse({"error": exc.code}, status_code=exc.status)

    @app.exception_handler(Exception)
    async def internal_error(_request, _exc):
        return JSONResponse({"error": "temporary_service_error"}, status_code=503)

    async def payload(request, allowed):
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise CommerceError("json_required", 415)
        try:
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result:
                        raise ValueError
                    result[key] = value
                return result
            value = json.loads(await request.body(), object_pairs_hook=pairs)
        except (ValueError, RecursionError) as exc:
            raise CommerceError("invalid_json", 400) from exc
        if not isinstance(value, dict) or value.keys() - allowed:
            raise CommerceError("invalid_request_fields")
        return value

    @app.get("/")
    async def home():
        return RedirectResponse(PREFIX)

    @app.get(PREFIX, response_class=HTMLResponse)
    async def index():
        return landing(settings.billing_enabled, settings.mode, settings.support_email)

    @app.get(PREFIX + "/app.js")
    async def javascript():
        return Response(JAVASCRIPT, media_type="application/javascript")

    @app.get(PREFIX + "/style.css")
    async def stylesheet():
        return Response(CSS, media_type="text/css")

    @app.get(PREFIX + "/health")
    async def health():
        with store.connect() as db:
            db.execute("SELECT 1").fetchone()
        return {"ready": True, "release": settings.release, "billing_enabled": settings.billing_enabled,
                "mode": settings.mode, "amount_cents": AMOUNT, "reports_per_pack": CREDITS}

    @app.post(PREFIX + "/api/workspaces")
    async def workspace(request: Request):
        await payload(request, set())
        store.rate("signup:" + ip_bucket(request), 3, 86400)
        store.rate("signup:global", 500, 86400)
        return store.create_workspace()

    @app.get(PREFIX + "/api/balance")
    async def balance(request: Request):
        return store.balance(auth(request))

    @app.post(PREFIX + "/api/checkout")
    async def checkout(request: Request):
        workspace = auth(request)
        value = await payload(request, {"idempotency_key"})
        store.rate("checkout:" + workspace, 20, 3600)
        store.rate("checkout:global", 100, 3600)
        return await run_in_threadpool(billing.checkout, workspace, value.get("idempotency_key"))

    @app.post(PREFIX + "/api/stripe/webhook")
    async def webhook(request: Request):
        return await run_in_threadpool(billing.event, await request.body(), request.headers.get("Stripe-Signature", ""))

    @app.post(PREFIX + "/api/stripe/webhook-test")
    async def test_webhook_observer(request: Request):
        # This observer holds a TEST signing secret only, never a setup/API key.
        # It proves signed provider delivery without touching live credit state.
        import stripe
        secret = os.environ.get("INSPECTOR_STRIPE_TEST_WEBHOOK_SECRET", "")
        if not secret:
            raise CommerceError("test_observer_unconfigured", 503)
        try:
            event = stripe.Webhook.construct_event(await request.body(), request.headers.get("Stripe-Signature", ""), secret, tolerance=300).to_dict()
        except (ValueError, stripe.SignatureVerificationError) as exc:
            raise CommerceError("invalid_webhook_signature", 400) from exc
        value = event.get("data", {}).get("object", {})
        if event.get("livemode") is not False or not event.get("type", "").startswith("checkout.session.") or value.get("metadata", {}).get("mcp_product") != "production-readiness-inspector":
            return {"ignored": True}
        if not re.fullmatch(r"evt_[A-Za-z0-9]+", event.get("id", "")) or not re.fullmatch(r"cs_test_[A-Za-z0-9]+", value.get("id", "")):
            raise CommerceError("invalid_event_identity", 400)
        with store.transaction() as db:
            db.execute("INSERT OR IGNORE INTO qualification_receipts VALUES (?,?,?,?)", (event["id"], event["type"], value["id"], time.time()))
        return {"signed_test_delivery_recorded": True, "live_credits_granted": 0}

    @app.post(PREFIX + "/api/reports")
    async def submit(request: Request):
        workspace = auth(request)
        value = await payload(request, {"project", "idempotency_key", "summary"})
        store.rate("reports:" + workspace, 60, 60)
        return store.submit(workspace, value.get("project"), value.get("idempotency_key"), value.get("summary"))

    @app.get(PREFIX + "/api/reports")
    async def history(request: Request):
        return {"reports": store.history(auth(request), request.query_params.get("project"))}

    @app.get(PREFIX + "/api/reports/{report_id}")
    async def get_report(report_id: str, request: Request):
        return store.report(auth(request), report_id)

    @app.get(PREFIX + "/api/reports/{report_id}/html", response_class=HTMLResponse)
    async def get_html(report_id: str, request: Request):
        return render_report(store.report(auth(request), report_id))

    @app.delete(PREFIX + "/api/reports/{report_id}")
    async def delete_report(report_id: str, request: Request):
        return store.delete_report(auth(request), report_id)

    @app.get(PREFIX + "/download/{name}")
    async def download(name: str):
        allowed = {"contentsweep_prodcheck-0.3.0-py3-none-any.whl", "contentsweep_prodcheck-0.3.0.tar.gz", "manifest.json"}
        if name not in allowed:
            raise CommerceError("download_not_found", 404)
        folder = Path(os.environ.get("INSPECTOR_ARTIFACT_DIR", ".mcp-products/inspector/dist"))
        path = folder / name
        if not path.is_file() or path.is_symlink():
            raise CommerceError("download_not_ready", 404)
        return FileResponse(path, filename=name)

    return app


def main():
    import uvicorn
    try:
        app = create_app()
    except (CommerceError, OSError):
        raise SystemExit("Inspector hosted configuration is unavailable; check private product settings.") from None
    uvicorn.run(app, host=os.environ.get("INSPECTOR_BIND", "127.0.0.1"), port=int(os.environ.get("INSPECTOR_PORT", "18183")), access_log=False, proxy_headers=False)


if __name__ == "__main__":
    main()
