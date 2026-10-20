"""Inspector-owned Checkout and signed-event adapter. No automatic customer charge."""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .commerce import AMOUNT, CREDITS, CommerceError, ReportStore
from .model import PRODUCT

OFFER = "release-reports-100-v1"
EVENTS = ["checkout.session.completed", "checkout.session.async_payment_succeeded", "checkout.session.async_payment_failed", "charge.refunded", "refund.updated"]


@dataclass(frozen=True)
class HostedSettings:
    database: Path
    base_url: str
    mode: str = "test"
    stripe_key: str = ""
    webhook_secret: str = ""
    price_id: str = ""
    account_id: str = ""
    payment_configuration: str = ""
    billing_enabled: bool = False
    tax_reference: str = ""
    proxy_network: str = ""
    release: str = "development"
    support_email: str = ""

    def __post_init__(self):
        parsed = urlparse(self.base_url)
        if self.mode not in {"test", "live"} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != "/inspector":
            raise CommerceError("invalid_hosted_configuration")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "testserver"}):
            raise CommerceError("https_required")
        if self.billing_enabled and (not self.stripe_key.startswith("rk_" + self.mode + "_") or not self.webhook_secret or not self.price_id or not self.account_id or not self.payment_configuration or not self.tax_reference):
            raise CommerceError("incomplete_billing_configuration")

    @classmethod
    def from_environment(cls):
        mode = os.environ.get("INSPECTOR_MODE", "test")
        return cls(database=Path(os.environ.get("INSPECTOR_DATABASE", ".mcp-products/inspector/hosted-test.sqlite")),
                   base_url=os.environ.get("INSPECTOR_BASE_URL", "http://127.0.0.1:18183/inspector"), mode=mode,
                   stripe_key=os.environ.get("INSPECTOR_STRIPE_" + mode.upper() + "_RUNTIME_KEY", ""),
                   webhook_secret=os.environ.get("INSPECTOR_STRIPE_" + mode.upper() + "_WEBHOOK_SECRET", ""),
                   price_id=os.environ.get("INSPECTOR_STRIPE_" + mode.upper() + "_PRICE_ID", ""),
                   account_id=os.environ.get("INSPECTOR_STRIPE_ACCOUNT_ID", ""),
                   payment_configuration=os.environ.get("INSPECTOR_STRIPE_" + mode.upper() + "_PAYMENT_CONFIGURATION", ""),
                   billing_enabled=os.environ.get("INSPECTOR_BILLING_ENABLED") == "true",
                   tax_reference=os.environ.get("INSPECTOR_TAX_REFERENCE", ""),
                   proxy_network=os.environ.get("INSPECTOR_TRUSTED_PROXY_NETWORK", ""),
                   release=os.environ.get("INSPECTOR_RELEASE", "development"),
                   support_email=os.environ.get("INSPECTOR_SUPPORT_EMAIL", ""))


class StripeGateway:
    def __init__(self, settings: HostedSettings):
        import stripe
        self.settings = settings
        self.client = stripe.StripeClient(settings.stripe_key, max_network_retries=1, http_client=stripe.RequestsClient(timeout=15))

    def request(self, method, path, **parameters):
        try:
            return self.client.raw_request(method, path, **parameters).data
        except Exception as exc:
            raise CommerceError("payment_provider_unavailable", 503) from exc

    def verify_catalog(self):
        account = self.request("get", "/v1/account")
        price = self.request("get", "/v1/prices/" + self.settings.price_id, expand=["product"])
        if account.get("id") != self.settings.account_id or (self.settings.mode == "live" and not account.get("charges_enabled")):
            raise CommerceError("stripe_account_unqualified", 503)
        product = price.get("product", {})
        if (price.get("livemode") is not (self.settings.mode == "live") or price.get("currency") != "usd"
                or price.get("unit_amount") != AMOUNT or price.get("type") != "one_time" or not price.get("active")
                or not isinstance(product, dict) or not product.get("active")
                or product.get("metadata", {}).get("mcp_product") != PRODUCT or product.get("metadata", {}).get("offer") != OFFER):
            raise CommerceError("stripe_catalog_mismatch", 503)
        configuration = self.request("get", "/v1/payment_method_configurations/" + self.settings.payment_configuration)
        enabled = {name for name, value in configuration.items() if isinstance(value, dict) and value.get("display_preference", {}).get("value") == "on"}
        if not configuration.get("active") or enabled != {"card"}:
            raise CommerceError("payment_method_configuration_changed", 503)

    def checkout(self, purchase: dict):
        self.verify_catalog()
        metadata = {"mcp_product": PRODUCT, "offer": OFFER, "purchase_id": purchase["id"], "workspace": purchase["workspace"]}
        # The provider key is purchase-stable; retrying an uncertain response
        # must use the exact same parameters, including this label.
        label = "inspector_reports_" + hashlib.sha256(purchase["id"].encode()).hexdigest()[:8]
        label = label[:-8] + "".join(chr(ord('a') + int(char, 16)) for char in label[-8:])
        params = {
            "mode": "payment", "line_items": [{"price": self.settings.price_id, "quantity": 1}],
            "client_reference_id": purchase["id"], "metadata": metadata,
            "payment_intent_data": {"metadata": metadata},
            "success_url": self.settings.base_url + "?checkout=complete",
            "cancel_url": self.settings.base_url + "?checkout=cancelled",
            "automatic_tax": {"enabled": False},
            "payment_method_configuration": self.settings.payment_configuration,
            "integration_identifier": label,
        }
        try:
            response = self.client.v1.checkout.sessions.create(params=params, options={"idempotency_key": "inspector:" + purchase["id"]})
            data = response.to_dict()
        except Exception as exc:
            raise CommerceError("payment_provider_unavailable", 503) from exc
        url = data.get("url", "")
        parsed = urlparse(url)
        if not re.fullmatch(r"cs_(?:test|live)_[A-Za-z0-9]+", data.get("id", "")) or parsed.scheme != "https" or parsed.hostname not in {"checkout.stripe.com", "checkout.contentsweep.ai"} or parsed.username or parsed.password or parsed.port not in {None, 443}:
            raise CommerceError("invalid_checkout_response", 503)
        return {"session_id": data["id"], "url": url}

    def session(self, session_id):
        if not isinstance(session_id, str) or not re.fullmatch(r"cs_(?:test|live)_[A-Za-z0-9]+", session_id):
            raise CommerceError("invalid_session_identity")
        return self.request("get", "/v1/checkout/sessions/" + session_id, expand=["line_items", "payment_intent.latest_charge"])

    def verify_event(self, raw: bytes, signature: str):
        import stripe
        try:
            event = stripe.Webhook.construct_event(raw, signature, self.settings.webhook_secret, tolerance=300)
            return event.to_dict()
        except (ValueError, stripe.SignatureVerificationError) as exc:
            raise CommerceError("invalid_webhook_signature", 400) from exc


class Billing:
    def __init__(self, settings: HostedSettings, store: ReportStore, gateway=None):
        self.settings, self.store, self.gateway = settings, store, gateway

    def checkout(self, workspace: str, key: str):
        if not self.settings.billing_enabled or self.gateway is None:
            raise CommerceError("checkout_not_enabled", 503)
        purchase = self.store.purchase(workspace, key)
        if purchase["status"] != "pending":
            raise CommerceError("purchase_already_completed_use_new_checkout", 409)
        result = self.gateway.checkout(purchase)
        self.store.bind_session(purchase["id"], result["session_id"])
        return {**result, "amount_cents": AMOUNT, "currency": "usd", "reports": CREDITS, "mode": self.settings.mode}

    def fulfill(self, session: dict, event_id: str, event_hash: str, event_type: str):
        metadata = session.get("metadata", {})
        if metadata.get("mcp_product") != PRODUCT or metadata.get("offer") != OFFER:
            return {"ignored": True}
        purchase = self.store.get_purchase(metadata.get("purchase_id", ""))
        if session.get("livemode") is not (self.settings.mode == "live") or metadata.get("workspace") != purchase["workspace"] or session.get("client_reference_id") != purchase["id"] or session.get("mode") != "payment":
            raise CommerceError("provider_purchase_identity_mismatch")
        if session.get("payment_status") != "paid" or session.get("status") != "complete":
            return {"pending_or_failed": True}
        line_items = session.get("line_items", {}).get("data", [])
        if (session.get("amount_total") != AMOUNT or session.get("amount_subtotal") != AMOUNT or session.get("currency") != "usd"
                or len(line_items) != 1 or line_items[0].get("price", {}).get("id") != self.settings.price_id
                or line_items[0].get("quantity") != 1 or line_items[0].get("amount_total") != AMOUNT):
            raise CommerceError("provider_purchase_amount_mismatch")
        intent = session.get("payment_intent")
        if not isinstance(intent, dict) or intent.get("status") != "succeeded" or intent.get("amount_received") != AMOUNT or intent.get("metadata", {}).get("purchase_id") != purchase["id"]:
            raise CommerceError("provider_payment_intent_mismatch")
        charge = intent.get("latest_charge")
        if not isinstance(charge, dict) or not charge.get("paid") or charge.get("amount") != AMOUNT or charge.get("amount_captured") != AMOUNT or charge.get("currency") != "usd" or charge.get("payment_intent") != intent.get("id"):
            raise CommerceError("provider_charge_mismatch")
        return self.store.apply_payment(purchase["id"], session["id"], intent["id"], charge.get("amount_refunded", 0), event_id, event_hash, event_type)

    def event(self, raw: bytes, signature: str):
        if self.gateway is None:
            raise CommerceError("webhook_unconfigured", 503)
        event = self.gateway.verify_event(raw, signature)
        if event.get("livemode") is not (self.settings.mode == "live"):
            raise CommerceError("webhook_mode_mismatch", 400)
        kind = event.get("type")
        if kind not in EVENTS:
            return {"ignored": True}
        value = event.get("data", {}).get("object", {})
        if kind.startswith("checkout.session."):
            if value.get("metadata", {}).get("mcp_product") != PRODUCT:
                return {"ignored": True}
            session = self.gateway.session(value.get("id"))
        else:
            # Refund/charge events lack Checkout identity. Resolve the payment
            # intent's owned metadata, then retrieve the owned session fresh.
            if kind == "refund.updated" and value.get("status") != "succeeded":
                return {"pending_or_failed": True}
            intent_id = value.get("payment_intent")
            if not isinstance(intent_id, str) or not re.fullmatch(r"pi_[A-Za-z0-9]+", intent_id):
                return {"ignored": True}
            intent = self.gateway.request("get", "/v1/payment_intents/" + intent_id)
            if intent.get("metadata", {}).get("mcp_product") != PRODUCT:
                return {"ignored": True}
            purchase = self.store.get_purchase(intent.get("metadata", {}).get("purchase_id", ""))
            if not purchase["session"]:
                raise CommerceError("payment_event_order_retry", 503)
            session = self.gateway.session(purchase["session"])
        if not isinstance(event.get("id"), str) or not event["id"].startswith("evt_"):
            raise CommerceError("invalid_event_identity", 400)
        return self.fulfill(session, event["id"], hashlib.sha256(raw).hexdigest(), kind)
