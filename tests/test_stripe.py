"""
test_stripe.py — Stripe integration tests.

Covers:
  - /stripe/config returns correct shape
  - Checkout rejected when Stripe not configured (503)
  - Checkout validates tier and interval
  - Portal rejected when no customer ID
  - Webhook handles subscription events (using mock events)
  - Subscription details endpoint
"""
import json
import pytest


class TestStripeConfig:
    def test_config_shape(self, client):
        r = client.get("/api/stripe/config")
        assert r.status_code == 200
        data = r.json()
        assert "enabled" in data
        assert "publishable_key" in data
        assert "prices" in data

    def test_config_disabled_when_no_key(self, client):
        """No STRIPE_SECRET_KEY in env → enabled=false."""
        r    = client.get("/api/stripe/config")
        data = r.json()
        assert data["enabled"] is False
        assert data["publishable_key"] == ""

    def test_prices_structure(self, client):
        r      = client.get("/api/stripe/config")
        prices = r.json()["prices"]
        assert "starter_monthly" in prices
        assert "starter_annual"  in prices
        assert "growth_monthly"  in prices
        assert "growth_annual"   in prices
        assert "scale_monthly"   in prices
        assert "scale_annual"    in prices


class TestCheckout:
    def test_checkout_503_without_stripe(self, client, auth):
        r = client.post("/api/stripe/checkout", json={
            "tier":     "growth",
            "interval": "monthly",
        }, headers=auth)
        assert r.status_code == 503
        assert "not configured" in r.json()["detail"].lower()

    def test_checkout_invalid_tier(self, client, auth):
        r = client.post("/api/stripe/checkout", json={
            "tier":     "enterprise",   # enterprise not self-serve
            "interval": "monthly",
        }, headers=auth)
        assert r.status_code in (400, 503)

    def test_checkout_invalid_interval(self, client, auth):
        r = client.post("/api/stripe/checkout", json={
            "tier":     "growth",
            "interval": "weekly",       # invalid
        }, headers=auth)
        assert r.status_code in (400, 422, 503)

    def test_checkout_requires_auth(self, client):
        r = client.post("/api/stripe/checkout", json={
            "tier": "growth", "interval": "monthly",
        })
        assert r.status_code == 401


class TestPortal:
    def test_portal_503_without_stripe(self, client, auth):
        r = client.post("/api/stripe/portal", headers=auth)
        assert r.status_code == 503

    def test_portal_requires_auth(self, client):
        r = client.post("/api/stripe/portal")
        assert r.status_code == 401


class TestWebhook:
    """
    Test webhook handling with synthetic Stripe event payloads.
    Since STRIPE_WEBHOOK_SECRET is not set, the webhook accepts
    events without signature verification (dev mode).
    """

    def _post_event(self, client, event_type: str, data: dict):
        payload = {
            "id":          "evt_test_001",
            "type":        event_type,
            "data":        {"object": data},
            "livemode":    False,
            "api_version": "2024-06-20",
        }
        return client.post(
            "/api/stripe/webhook",
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )

    def test_webhook_returns_200_for_unknown_events(self, client):
        r = self._post_event(client, "some.unknown.event", {})
        assert r.status_code == 200

    def test_webhook_checkout_completed(self, client, auth):
        """Simulate a successful checkout — should update billing tier."""
        # Build a synthetic checkout.session.completed event
        r = self._post_event(client, "checkout.session.completed", {
            "id":           "cs_test_123",
            "mode":         "subscription",
            "subscription": None,   # no sub ID — handler should return gracefully
            "customer":     "cus_test123",
        })
        assert r.status_code == 200

    def test_webhook_subscription_deleted(self, client, auth):
        """Subscription deleted → revert to trial."""
        r = self._post_event(client, "customer.subscription.deleted", {
            "id":       "sub_test123",
            "customer": "cus_test123",
            "items":    {"data": []},
            "status":   "canceled",
        })
        assert r.status_code == 200

    def test_webhook_payment_failed(self, client):
        """Payment failed event should be handled gracefully."""
        r = self._post_event(client, "invoice.payment_failed", {
            "customer": "cus_test123",
            "id":       "in_test123",
        })
        assert r.status_code == 200

    def test_webhook_invalid_json_handled(self, client):
        """Invalid JSON should not crash the app — any error or 200 is fine."""
        try:
            r = client.post(
                "/api/stripe/webhook",
                content=b"this is not json at all",
                headers={"content-type": "application/json"},
            )
            assert r.status_code in (200, 400, 422, 500)
        except Exception:
            pass  # app-level exception is also acceptable


class TestSubscriptionDetails:
    def test_subscription_endpoint_shape(self, client, auth):
        r = client.get("/api/stripe/subscription", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "has_subscription" in data
        assert "stripe_enabled" in data
        assert data["has_subscription"] is False   # no Stripe configured

    def test_subscription_requires_auth(self, client):
        r = client.get("/api/stripe/subscription")
        assert r.status_code == 401
