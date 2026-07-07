"""
test_webhooks.py — Webhook configuration and delivery tests.

Covers:
  - Save and retrieve webhook_url / webhook_secret via settings
  - webhook_service.fire() no-ops when no URL configured
  - webhook_service.fire() sends signed POST; delivery failure is graceful
  - Asset creation fires webhook (verifiable via mock)
"""
import hashlib
import hmac
import json
import time
from unittest.mock import patch, MagicMock


def _uid():
    return int(time.time() * 1000) % 99999999


def _tenant_headers(auth, tenant):
    return {**auth, "host": f"{tenant['slug']}.localhost"}


class TestWebhookSettings:
    def test_webhook_url_field_in_settings(self, client, auth, tenant):
        h = _tenant_headers(auth, tenant)
        r = client.get("/api/settings", headers=h)
        assert r.status_code == 200
        assert "webhook_url" in r.json()
        assert "webhook_secret" in r.json()

    def test_save_and_retrieve_webhook_url(self, client, auth, tenant):
        h = _tenant_headers(auth, tenant)
        s = client.get("/api/settings", headers=h).json()
        body = {**s,
                "webhook_url": "https://hooks.example.com/tether",
                "webhook_secret": "supersecret123"}
        r = client.put("/api/settings", json=body, headers=h)
        assert r.status_code == 200
        updated = client.get("/api/settings", headers=h).json()
        assert updated["webhook_url"] == "https://hooks.example.com/tether"
        assert updated["webhook_secret"] == "supersecret123"

    def test_clear_webhook_url(self, client, auth, tenant):
        h = _tenant_headers(auth, tenant)
        s = client.get("/api/settings", headers=h).json()
        body = {**s, "webhook_url": None, "webhook_secret": None}
        r = client.put("/api/settings", json=body, headers=h)
        assert r.status_code == 200
        updated = client.get("/api/settings", headers=h).json()
        assert updated["webhook_url"] == ""


class TestWebhookService:
    def test_fire_no_ops_when_no_url(self):
        from webhook_service import fire
        tenant = MagicMock()
        tenant.webhook_url = None
        assert fire(tenant, "asset.created", {"asset_tag": "TEST-001"}) is False

    def test_fire_no_ops_when_tenant_is_none(self):
        from webhook_service import fire
        assert fire(None, "asset.created", {}) is False

    def test_fire_sends_signed_post(self):
        from webhook_service import fire
        secret = "mysecret"
        captured = []

        def mock_urlopen(req, timeout=10):
            captured.append(req)
            resp = MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            resp.status = 200
            return resp

        tenant = MagicMock()
        tenant.webhook_url = "https://hooks.example.com/test"
        tenant.webhook_secret = secret
        tenant.slug = "testco"

        with patch("urllib.request.urlopen", mock_urlopen):
            result = fire(tenant, "asset.created", {"asset_tag": "T-001", "name": "Test"})

        assert result is True
        assert len(captured) == 1
        req = captured[0]
        body = req.data
        sig_header = req.get_header("X-tether-signature")
        assert sig_header is not None
        expected = "sha256=" + hmac.new(secret.encode(), body, digestmod=hashlib.sha256).hexdigest()
        assert sig_header == expected
        payload = json.loads(body)
        assert payload["event"] == "asset.created"
        assert payload["tenant"] == "testco"
        assert "timestamp" in payload

    def test_fire_graceful_on_http_error(self):
        from webhook_service import fire

        def mock_urlopen(req, timeout=10):
            raise Exception("Connection refused")

        tenant = MagicMock()
        tenant.webhook_url = "https://hooks.example.com/bad"
        tenant.webhook_secret = None
        tenant.slug = "badco"

        with patch("urllib.request.urlopen", mock_urlopen):
            result = fire(tenant, "asset.created", {})

        assert result is False


class TestWebhookFiredOnAssetCreate:
    def test_webhook_called_on_asset_create(self, client, auth, tenant):
        from unittest.mock import patch as _patch
        h = _tenant_headers(auth, tenant)
        calls = []

        def fake_fire(t, event, payload):
            calls.append((event, payload))
            return True

        uid = _uid()
        with _patch("webhook_service.fire", fake_fire):
            r = client.post("/api/assets", json={
                "asset_tag": f"WH-{uid}", "name": "Webhook Test", "status": "available",
            }, headers=h)
        assert r.status_code == 200
        assert any(ev == "asset.created" for ev, _ in calls)
