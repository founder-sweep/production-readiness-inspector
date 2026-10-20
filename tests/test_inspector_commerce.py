from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest

from mcp_products.inspector import inspect_repository
from mcp_products.inspector.billing import OFFER, Billing, HostedSettings, StripeGateway
from mcp_products.inspector.commerce import (
    AMOUNT,
    PRODUCT,
    CommerceError,
    ReportStore,
    summarize_report,
    validate_summary,
)
from mcp_products.inspector.hosted import create_app, render_report

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def summary():
    return summarize_report(inspect_repository(ROOT / "examples/inspector/defective").to_dict())


@pytest.fixture
def store(tmp_path):
    return ReportStore(tmp_path / "store.sqlite", "test")


def workspace(store):
    value = store.create_workspace()
    return value["workspace_id"], value["api_key"]


def test_metadata_whitelist_excludes_arbitrary_source_and_facts(summary):
    assert "evidence" not in json.dumps(summary) and "remediation" not in json.dumps(summary)
    altered = copy.deepcopy(summary)
    altered["source"] = "PRIVATE"
    with pytest.raises(CommerceError, match="invalid_summary_fields"):
        validate_summary(altered)
    altered = copy.deepcopy(summary)
    altered["findings"][0]["fact"] = "PRIVATE"
    with pytest.raises(CommerceError, match="invalid_finding_fields"):
        validate_summary(altered)


def test_report_retry_baseline_and_tenant_isolation(store, summary):
    first, token = workspace(store)
    second, _ = workspace(store)
    assert store.authenticate(token) == first
    report = store.submit(first, "api", "release-001", summary)
    again = store.submit(first, "api", "release-001", summary)
    assert report["id"] == again["id"] and again["billed_reports"] == 0
    assert store.balance(first)["reports_remaining"] == 2
    fixed = copy.deepcopy(summary)
    fixed["findings"] = []
    next_report = store.submit(first, "api", "release-002", fixed)
    assert len(next_report["comparison"]["resolved"]) == len(summary["findings"])
    with pytest.raises(CommerceError, match="report_not_found"):
        store.report(second, report["id"])
    assert not store.history(second)
    with pytest.raises(CommerceError, match="idempotency_payload_conflict"):
        store.submit(first, "api", "release-001", fixed)


def test_concurrent_last_credit_cannot_be_overspent(store, summary):
    first, _ = workspace(store)
    store.submit(first, "api", "release-001", summary)
    store.submit(first, "api", "release-002", summary)
    def submit(number):
        try:
            store.submit(first, "api", "parallel-" + str(number), summary)
            return "paid"
        except CommerceError as exc:
            return exc.code
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        outcomes = list(executor.map(submit, range(6)))
    assert outcomes.count("paid") == 1
    assert outcomes.count("insufficient_report_credits") == 5
    assert store.balance(first)["reports_remaining"] == 0


def test_policy_mismatch_incomplete_and_unknown_summary_are_free(store, summary):
    first, _ = workspace(store)
    store.submit(first, "api", "release-001", summary)
    changed = copy.deepcopy(summary)
    changed["scope_fingerprint"] = "sha256:" + "b" * 64
    with pytest.raises(CommerceError, match="baseline_policy_changed"):
        store.submit(first, "api", "release-002", changed)
    changed["coverage"]["python"] = "partial"
    with pytest.raises(CommerceError, match="incomplete_or_invalid_coverage"):
        store.submit(first, "other", "release-003", changed)
    assert store.balance(first)["reports_remaining"] == 2


def test_payment_refund_retries_and_old_snapshots_are_monotonic(store):
    first, _ = workspace(store)
    purchase = store.purchase(first, "checkout-001")
    store.apply_payment(purchase["id"], "cs_test_one", "pi_one", 0, "evt_one", "hash1", "checkout.session.completed")
    store.apply_payment(purchase["id"], "cs_test_one", "pi_one", 0, "evt_one", "hash1", "checkout.session.completed")
    assert store.balance(first)["reports_remaining"] == 103
    store.apply_payment(purchase["id"], "cs_test_one", "pi_one", 950, "evt_refund", "hash2", "charge.refunded")
    assert store.balance(first)["reports_remaining"] == 53
    store.apply_payment(purchase["id"], "cs_test_one", "pi_one", 0, "evt_delayed", "hash3", "checkout.session.completed")
    assert store.balance(first)["reports_remaining"] == 53
    store.apply_payment(purchase["id"], "cs_test_one", "pi_one", AMOUNT, "evt_full", "hash4", "charge.refunded")
    assert store.balance(first)["reports_remaining"] == 3
    with pytest.raises(CommerceError, match="event_identity_conflict"):
        store.apply_payment(purchase["id"], "cs_test_one", "pi_one", 0, "evt_one", "different", "checkout.session.completed")


def settings(tmp_path, *, mode="test"):
    return HostedSettings(tmp_path / "hosted.sqlite", "http://testserver/inspector", mode=mode,
                          stripe_key="rk_" + mode + "_" + "fixture", webhook_secret="whsec_" + "fixture",
                          price_id="price_fixture", account_id="acct_fixture", payment_configuration="pmc_fixture",
                          billing_enabled=True, tax_reference="fixture-only")


def paid_session(purchase):
    return {"id": "cs_test_fixture", "livemode": False, "status": "complete", "mode": "payment", "payment_status": "paid",
            "client_reference_id": purchase["id"], "metadata": {"mcp_product": PRODUCT, "offer": OFFER, "purchase_id": purchase["id"], "workspace": purchase["workspace"]},
            "amount_total": AMOUNT, "amount_subtotal": AMOUNT, "currency": "usd",
            "line_items": {"data": [{"price": {"id": "price_fixture"}, "quantity": 1, "amount_total": AMOUNT}]},
            "payment_intent": {"id": "pi_fixture", "status": "succeeded", "amount_received": AMOUNT, "metadata": {"purchase_id": purchase["id"]}, "latest_charge": {"id": "ch_fixture", "paid": True, "amount": AMOUNT, "amount_captured": AMOUNT, "currency": "usd", "payment_intent": "pi_fixture", "amount_refunded": 0}}}


@pytest.mark.parametrize("field,value", [("livemode", True), ("amount_total", 1), ("currency", "eur"), ("mode", "subscription"), ("client_reference_id", "other")])
def test_provider_wrong_mode_price_amount_identity_never_grants(tmp_path, store, field, value):
    first, _ = workspace(store)
    purchase = store.purchase(first, "checkout-001")
    session = paid_session(purchase)
    session[field] = value
    with pytest.raises(CommerceError):
        Billing(settings(tmp_path), store).fulfill(session, "evt_one", "hash", "checkout.session.completed")
    assert store.balance(first)["reports_remaining"] == 3


def test_unpaid_completed_checkout_and_browser_return_do_not_fulfill(tmp_path, store):
    first, _ = workspace(store)
    purchase = store.purchase(first, "checkout-001")
    session = paid_session(purchase)
    session["payment_status"] = "unpaid"
    result = Billing(settings(tmp_path), store).fulfill(session, "evt_one", "hash", "checkout.session.completed")
    assert result["pending_or_failed"]
    assert store.balance(first)["reports_remaining"] == 3


def test_webhook_signature_and_expiry_are_verified(tmp_path):
    gateway = StripeGateway(settings(tmp_path))
    raw = json.dumps({"id": "evt_fixture", "object": "event", "type": "checkout.session.completed", "livemode": False, "data": {"object": {}}}).encode()
    def signature(timestamp):
        value = hmac.new(gateway.settings.webhook_secret.encode(), str(timestamp).encode() + b"." + raw, hashlib.sha256).hexdigest()
        return f"t={timestamp},v1={value}"
    assert gateway.verify_event(raw, signature(int(time.time())))["id"] == "evt_fixture"
    with pytest.raises(CommerceError, match="invalid_webhook_signature"):
        gateway.verify_event(raw, signature(int(time.time()) - 1000))
    with pytest.raises(CommerceError, match="invalid_webhook_signature"):
        gateway.verify_event(raw + b" ", signature(int(time.time())))


def test_backup_restore_and_deleted_receipts_do_not_double_bill(tmp_path, store, summary):
    first, _ = workspace(store)
    report = store.submit(first, "api", "release-001", summary)
    backup = tmp_path / "restored.sqlite"
    store.backup(backup)
    restored = ReportStore(backup, "test")
    assert restored.report(first, report["id"])["summary"] == summary
    store.delete_report(first, report["id"])
    again = store.submit(first, "api", "release-001", summary)
    assert again["expired"] and again["billed_reports"] == 0
    assert store.balance(first)["reports_remaining"] == 2
    with pytest.raises(CommerceError, match="database_mode_mismatch"):
        ReportStore(backup, "live")


def test_public_api_full_flow_and_browser_headers(tmp_path, summary):
    from fastapi.testclient import TestClient
    config = HostedSettings(tmp_path / "api.sqlite", "http://testserver/inspector")
    with TestClient(create_app(config)) as client:
        landing = client.get("/inspector")
        assert landing.status_code == 200 and "$19" in landing.text
        assert "frame-ancestors 'none'" in landing.headers["Content-Security-Policy"]
        assert client.post("/inspector/api/workspaces", json={}, headers={"Origin": "https://untrusted.example"}).status_code == 403
        created = client.post("/inspector/api/workspaces", json={}).json()
        headers = {"Authorization": "Bearer " + created["api_key"]}
        assert client.get("/inspector/api/balance").status_code == 401
        body = {"project": "service", "idempotency_key": "release-001", "summary": summary}
        response = client.post("/inspector/api/reports", json=body, headers=headers)
        assert response.status_code == 200
        report = response.json()
        assert client.get("/inspector/api/reports/" + report["id"] + "/html", headers=headers).status_code == 200
        assert client.get("/inspector/api/balance", headers=headers).json()["reports_remaining"] == 2
        client.get("/inspector?checkout=complete")
        assert client.get("/inspector/api/balance", headers=headers).json()["reports_remaining"] == 2
        assert client.post("/inspector/api/checkout", json={"idempotency_key": "checkout-001"}, headers=headers).status_code == 503
        assert client.post("/inspector/api/reports", content=b"x" * 2_000_001, headers=headers).status_code == 413


def test_report_html_escapes_paths_and_never_contains_customer_fact(store, summary):
    first, _ = workspace(store)
    altered = copy.deepcopy(summary)
    altered["findings"][0]["path"] = '<script>alert("x")</script>.py'
    report = store.submit(first, "service", "release-001", altered)
    rendered = render_report(report)
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered


def test_signed_payment_callback_grants_once_and_rejects_wrong_price(tmp_path, store, monkeypatch):
    first, _ = workspace(store)
    purchase = store.purchase(first, "checkout-001")
    config = settings(tmp_path)
    gateway = StripeGateway(config)
    session = paid_session(purchase)
    monkeypatch.setattr(gateway, "session", lambda _session: session)
    event = {"id": "evt_actualfixture", "object": "event", "livemode": False, "type": "checkout.session.completed", "data": {"object": {"id": session["id"], "metadata": session["metadata"]}}}
    raw = json.dumps(event).encode()
    timestamp = int(time.time())
    signature = hmac.new(config.webhook_secret.encode(), str(timestamp).encode() + b"." + raw, hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={signature}"
    billing = Billing(config, store, gateway)
    assert billing.event(raw, header)["granted_reports"] == 100
    assert billing.event(raw, header)["duplicate"]
    assert store.balance(first)["reports_remaining"] == 103
    session["line_items"]["data"][0]["price"]["id"] = "price_wrong"
    with pytest.raises(CommerceError, match="provider_purchase_amount_mismatch"):
        billing.fulfill(session, "evt_other", "hash", "checkout.session.completed")


def test_internal_purchase_classification_is_frozen(store):
    created = store.create_workspace(classification="internal")
    first = created["workspace_id"]
    purchase = store.purchase(first, "checkout-internal")
    with store.transaction() as db:
        db.execute("UPDATE workspaces SET classification='customer' WHERE id=?", (first,))
    assert store.get_purchase(purchase["id"])["classification"] == "internal"


def test_test_webhook_observer_has_no_live_fulfillment(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    config = HostedSettings(tmp_path / "observer.sqlite", "http://testserver/inspector", mode="live")
    secret = "whsec_" + "observerfixture"
    monkeypatch.setenv("INSPECTOR_STRIPE_TEST_WEBHOOK_SECRET", secret)
    app = create_app(config)
    raw = json.dumps({"id": "evt_observer", "object": "event", "livemode": False, "type": "checkout.session.completed", "data": {"object": {"id": "cs_test_observer", "metadata": {"mcp_product": PRODUCT}}}}).encode()
    timestamp = int(time.time())
    signature = hmac.new(secret.encode(), str(timestamp).encode() + b"." + raw, hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        response = client.post("/inspector/api/stripe/webhook-test", content=raw, headers={"Stripe-Signature": f"t={timestamp},v1={signature}"})
        assert response.status_code == 200 and response.json()["live_credits_granted"] == 0
        with app.state.store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM qualification_receipts").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM ledger").fetchone()[0] == 0


def test_refunded_spent_credits_hold_use_without_an_auto_charge(store, summary):
    first, _ = workspace(store)
    purchase = store.purchase(first, "checkout-001")
    store.apply_payment(purchase["id"], "cs_test_one", "pi_one", 0, "evt_one", "hash", "checkout.session.completed")
    for number in range(5):
        store.submit(first, "api", "release-" + str(number), summary)
    store.apply_payment(purchase["id"], "cs_test_one", "pi_one", AMOUNT, "evt_refund", "hash2", "charge.refunded")
    assert store.balance(first)["revoked_credit_debt"] == 2
    with pytest.raises(CommerceError, match="insufficient_report_credits"):
        store.submit(first, "api", "release-next", summary)


@pytest.mark.parametrize("domain,accepted", [("checkout.stripe.com", True), ("checkout.contentsweep.ai", True), ("checkout.attacker.example", False)])
def test_provider_custom_checkout_domain_and_retry_parameters(tmp_path, store, monkeypatch, domain, accepted):
    from types import SimpleNamespace
    first, _ = workspace(store)
    purchase = store.purchase(first, "checkout-domain")
    gateway = StripeGateway(settings(tmp_path))
    calls = []
    def create(*, params, options):
        calls.append((params, options))
        return SimpleNamespace(to_dict=lambda: {"id": "cs_test_domain", "url": "https://" + domain + "/checkout"})
    gateway.client = SimpleNamespace(v1=SimpleNamespace(checkout=SimpleNamespace(sessions=SimpleNamespace(create=create))))
    monkeypatch.setattr(gateway, "verify_catalog", lambda: None)
    if not accepted:
        with pytest.raises(CommerceError, match="invalid_checkout_response"):
            gateway.checkout(purchase)
        return
    gateway.checkout(purchase)
    gateway.checkout(purchase)
    assert calls[0] == calls[1]
    params = calls[0][0]
    assert "payment_method_types" not in params
    assert params["payment_method_configuration"] == "pmc_fixture"
    assert params["integration_identifier"][-8:].isalpha()
