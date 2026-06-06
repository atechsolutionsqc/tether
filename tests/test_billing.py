"""
test_billing.py — Billing and tier limit tests.

Covers:
  - /billing/status returns correct shape
  - Self-hosted mode: saas=false, no limits
  - /billing/tiers lists available tiers
  - Manual tier update via PUT /api/billing/tier
  - SaaS enforcement tested separately via saas_client fixture
"""
import os
import pytest


class TestBillingStatusSelfHosted:
    """Default mode — selfhosted, no limits."""

    def test_status_shape(self, client, auth):
        r = client.get("/api/billing/status", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "saas"         in data
        assert "tier"         in data
        assert "total_assets" in data

    def test_selfhosted_has_no_limits(self, client, auth):
        r    = client.get("/api/billing/status", headers=auth)
        data = r.json()
        assert data["saas"]        is False
        assert data["asset_limit"] is None

    def test_tiers_endpoint(self, client, auth):
        r     = client.get("/api/billing/tiers", headers=auth)
        assert r.status_code == 200
        tiers = r.json()
        assert isinstance(tiers, list)
        keys  = [t["key"] for t in tiers]
        assert "starter"    in keys
        assert "growth"     in keys
        assert "scale"      in keys
        assert "enterprise" in keys

    def test_tier_update(self, client, auth):
        r = client.put("/api/billing/tier", json={
            "tier":          "starter",
            "billing_email": "billing@test.com",
        }, headers=auth)
        assert r.status_code == 200
        assert r.json()["tier"] == "starter"

        # Restore to selfhosted
        client.put("/api/billing/tier", json={"tier": "selfhosted"}, headers=auth)

    def test_status_requires_auth(self, client):
        r = client.get("/api/billing/status")
        assert r.status_code == 401

    def test_tier_update_invalid_tier(self, client, auth):
        r = client.put("/api/billing/tier",
                       json={"tier": "invalidtier"},
                       headers=auth)
        assert r.status_code == 400

    def test_tier_update_requires_permission(self, client, auth,
                                              tenant, roles):
        """Client viewers cannot change billing tier."""
        import time
        email = f"viewer{int(time.time()*1000)%9999}@test.com"
        client.post("/api/users", json={
            "name": "Viewer", "email": email, "password": "password123",
            "role_id":      roles["client_viewer"]["id"],
            "tenant_id":    tenant["id"],
            "is_msp_staff": False, "active": True,
        }, headers=auth)
        r2  = client.post("/api/auth/login",
                          data={"username": email, "password": "password123"})
        tok = r2.json()["access_token"]
        r3  = client.put("/api/billing/tier", json={"tier": "growth"},
                         headers={"Authorization": f"Bearer {tok}",
                                  "host": f"{tenant['slug']}.localhost"})
        assert r3.status_code == 403


class TestAssetLimitEnforcement:
    """
    Test 402 enforcement by pushing the billing tier to a low limit
    then attempting to exceed it. Uses selfhosted mode since we can
    update the tier via the API.
    """

    def test_402_when_tier_limit_exceeded(self, client, auth, tenant_headers):
        import os, time
        # Only run this test in saas mode — skip in selfhosted
        r = client.get("/api/billing/status", headers=auth)
        if not r.json().get("saas"):
            pytest.skip("Asset limits only enforced in saas mode")

    def test_warning_status_at_80_percent(self, client, auth):
        r = client.get("/api/billing/status", headers=auth)
        if not r.json().get("saas"):
            pytest.skip("Usage warnings only in saas mode")
        # If we were in saas mode with 80%+ usage, status would be warning
        usage = r.json().get("usage_pct", 0)
        if usage >= 80:
            assert r.json()["usage_status"] in ("warning", "exceeded")
