#!/usr/bin/env python3
"""Inspector-owned catalog/webhook setup. No payments, no root env changes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import tempfile
from pathlib import Path

import stripe
from stripe._api_version import _ApiVersion

from mcp_products.inspector.billing import EVENTS, OFFER
from mcp_products.inspector.commerce import AMOUNT, CREDITS, PRODUCT


def env_file(path):
    return {key.strip(): value.strip().strip("\"'") for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#") for key, separator, value in [line.partition("=")] if separator}


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def provision(root, *, mode, base_url, expected_account, apply):
    values = env_file(root / "ops/secrets/mcp-products.env")
    source = "STRIPE_LIVE_SETUP_KEY" if mode == "live" else "STRIPE_SECRET_KEY"
    key = values.get(source, "")
    if not key.startswith("rk_" + mode + "_"):
        raise ValueError("mode-specific restricted setup credential unavailable")
    client = stripe.StripeClient(key, max_network_retries=1)
    runtime = root / ".mcp-products/inspector"
    path = runtime / ("stripe-" + mode + ".private.json")
    state = json.loads(path.read_text()) if path.exists() else {}
    def save():
        private_write(path, json.dumps(state, indent=2))
    if mode == "live":
        account = client.raw_request("get", "/v1/account").data
        if account["id"] != expected_account or not account.get("charges_enabled"):
            raise ValueError("account identity or readiness mismatch")
    else:
        # Existing sandbox key lacks account-read scope. Match the retained
        # owner-created sandbox identity, never infer it from a live key.
        previous = json.loads((root / ".mcp-products/stripe-test-setup.json").read_text())
        if previous.get("stripe_account_id") != expected_account or not previous.get("account_verification"):
            raise ValueError("existing sandbox account review required")
    webhook_url = base_url + ("/api/stripe/webhook" if mode == "live" else "/api/stripe/webhook-test")
    preview = {"product": PRODUCT, "mode": mode, "account": expected_account, "amount_cents": AMOUNT,
               "currency": "usd", "credits": CREDITS, "automatic_tax": False,
               "webhook_url": webhook_url, "creates_charge": False, "apply": apply}
    if not apply:
        return preview
    lookup = "contentsweep_inspector_" + mode + "_reports100_v1"
    matches = client.v1.prices.list(params={"lookup_keys": [lookup], "expand": ["data.product"]}).to_dict()["data"]
    if len(matches) > 1:
        raise ValueError("ambiguous owned lookup")
    if matches:
        price = matches[0]
        product = price["product"]
    else:
        product = client.v1.products.create(params={"name": "Inspector — 100 hosted release reports",
            "description": "Private 30-day static release report history, baseline comparisons and HTML/JSON export. Local scanning is free.",
            "metadata": {"mcp_product": PRODUCT, "offer": OFFER}}, options={"idempotency_key": lookup + ":product"}).to_dict()
        state["product_id"] = product["id"]
        save()
        price = client.v1.prices.create(params={"product": product["id"], "currency": "usd", "unit_amount": AMOUNT, "lookup_key": lookup,
            "metadata": {"mcp_product": PRODUCT, "offer": OFFER, "credits": str(CREDITS)}}, options={"idempotency_key": lookup + ":price"}).to_dict()
    if product.get("metadata", {}).get("mcp_product") != PRODUCT or product.get("metadata", {}).get("offer") != OFFER or price.get("unit_amount") != AMOUNT or price.get("currency") != "usd" or price.get("livemode") is not (mode == "live"):
        raise ValueError("owned catalog mismatch")
    state.update({"product_id": product["id"], "price_id": price["id"], "account_id": expected_account, "mode": mode})
    save()
    if "webhook_secret" not in state:
        if "webhook_nonce" not in state:
            state["webhook_nonce"] = secrets.token_hex(16)
            save()
        endpoint = client.v1.webhook_endpoints.create(params={"url": webhook_url, "enabled_events": EVENTS,
            "api_version": _ApiVersion.CURRENT, "metadata": {"mcp_product": PRODUCT, "offer": OFFER}},
            options={"idempotency_key": lookup + ":webhook:" + state["webhook_nonce"]}).to_dict()
        state.update({"webhook_id": endpoint["id"], "webhook_secret": endpoint["secret"], "webhook_url": webhook_url})
        save()
    elif state.get("webhook_url") != webhook_url:
        raise ValueError("existing owned endpoint needs an explicit URL migration")
    if mode == "live":
        runtime_key = values.get("STRIPE_LIVE_SECRET_KEY", "")
        if not runtime_key.startswith("rk_live_") or runtime_key == key:
            raise ValueError("distinct live runtime credential unavailable")
        config = values.get("STRIPE_LIVE_PAYMENT_METHOD_CONFIGURATION", "")
        if not config:
            raise ValueError("qualified business payment-method configuration unavailable")
        settings = {"INSPECTOR_MODE": "live", "INSPECTOR_BASE_URL": base_url, "INSPECTOR_DATABASE": "/data/inspector-live.sqlite",
                    "INSPECTOR_STRIPE_ACCOUNT_ID": expected_account, "INSPECTOR_STRIPE_LIVE_RUNTIME_KEY": runtime_key,
                    "INSPECTOR_STRIPE_LIVE_PRICE_ID": state["price_id"], "INSPECTOR_STRIPE_LIVE_WEBHOOK_SECRET": state["webhook_secret"],
                    "INSPECTOR_STRIPE_LIVE_PAYMENT_CONFIGURATION": config, "INSPECTOR_BILLING_ENABLED": "false",
                    "INSPECTOR_TAX_REFERENCE": "existing-owner-cloud-only-no-collection-2026-10-16",
                    "INSPECTOR_BIND": "0.0.0.0", "INSPECTOR_PORT": "8080", "INSPECTOR_ARTIFACT_DIR": "/app/dist"}
        from email.utils import parseaddr
        settings["INSPECTOR_SUPPORT_EMAIL"] = parseaddr(values.get("SMTP_FROM", ""))[1]
        test_state = runtime / "stripe-test.private.json"
        if test_state.exists():
            test_values = json.loads(test_state.read_text())
            settings["INSPECTOR_STRIPE_TEST_WEBHOOK_SECRET"] = test_values["webhook_secret"]
        private_write(runtime / "hosted-live.env", "\n".join(name + "=" + value for name, value in settings.items()) + "\n")
    return {**preview, "product_id": state["product_id"], "price_id": state["price_id"],
            "webhook_id": state["webhook_id"], "webhook_signing_secret_saved": True,
            "setup_key_uploaded": False, "billing_enabled": False,
            "setup_key_fingerprint": hashlib.sha256(key.encode()).hexdigest()[:12]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["test", "live"], required=True)
    parser.add_argument("--expected-account", required=True)
    parser.add_argument("--base-url", default="https://inspector.contentsweep.ai/inspector")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    import subprocess
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    try:
        print(json.dumps(provision(root, mode=args.mode, base_url=args.base_url, expected_account=args.expected_account, apply=args.apply), indent=2))
    except Exception as exc:  # noqa: BLE001 - provider exceptions must not reveal credentials
        print(json.dumps({"error": "inspector_catalog_setup_failed", "error_class": type(exc).__name__}))
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
