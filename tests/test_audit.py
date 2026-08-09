"""
tests/test_audit.py — Audit log integration tests.

Verifies that key actions write audit entries and that
the GET /api/admin/audit endpoint works correctly.
"""
import time
import pytest


class TestAuditWrites:
    def test_asset_create_writes_entry(self, client, auth, tenant, tenant_headers):
        tag = f"AUD-{int(time.time() * 1000) % 999999:06d}"
        client.post("/api/assets", json={
            "asset_tag": tag, "name": "Audit test asset", "status": "available",
        }, headers=tenant_headers)

        r = client.get("/api/admin/audit?action=asset.create&limit=20", headers=auth)
        assert r.status_code == 200
        items = r.json()["items"]
        tags = [e["resource_id"] for e in items]
        assert tag in tags

    def test_user_delete_writes_entry(self, client, auth, tenant, roles):
        # create a user then delete it
        uid = int(time.time() * 1000) % 999999
        email = f"audit_del_{uid}@test.com"
        role_id = next(iter(roles.values()))["id"]
        cr = client.post("/api/users", json={
            "name": "AuditDel", "email": email,
            "password": "Secure123!", "role_id": role_id,
            "tenant_id": tenant["id"], "is_msp_staff": False, "active": True,
        }, headers=auth)
        assert cr.status_code == 200
        user_id = cr.json()["id"]

        dr = client.delete(f"/api/users/{user_id}", headers=auth)
        assert dr.status_code == 200

        r = client.get("/api/admin/audit?action=user.delete&limit=20", headers=auth)
        assert r.status_code == 200
        items = r.json()["items"]
        resource_ids = [e["resource_id"] for e in items]
        assert email in resource_ids

    def test_login_failed_writes_entry(self, client, auth):
        client.post("/api/auth/login", data={
            "username": "nonexistent@audit.test", "password": "wrongpass"
        })
        r = client.get("/api/admin/audit?action=auth.login_failed&limit=20", headers=auth)
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(e["resource_id"] == "nonexistent@audit.test" for e in items)

    def test_login_success_writes_entry(self, client, auth):
        r = client.get("/api/admin/audit?action=auth.login&limit=20", headers=auth)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) > 0
        assert all(e["action"] == "auth.login" for e in items)


class TestAuditEndpoint:
    def test_response_shape(self, client, auth):
        r = client.get("/api/admin/audit", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["items"], list)

    def test_requires_auth(self, client):
        r = client.get("/api/admin/audit")
        assert r.status_code == 401

    def test_action_filter(self, client, auth):
        r = client.get("/api/admin/audit?action=auth.login", headers=auth)
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(e["action"] == "auth.login" for e in items)

    def test_limit_param(self, client, auth):
        r = client.get("/api/admin/audit?limit=2", headers=auth)
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 2

    def test_limit_max_500(self, client, auth):
        r = client.get("/api/admin/audit?limit=501", headers=auth)
        assert r.status_code == 422

    def test_entry_fields(self, client, auth):
        r = client.get("/api/admin/audit?limit=1", headers=auth)
        assert r.status_code == 200
        items = r.json()["items"]
        if items:
            e = items[0]
            for field in ("id", "timestamp", "actor_email", "action",
                          "resource", "resource_id", "detail", "ip_address"):
                assert field in e

    def test_csv_export_requires_auth(self, client):
        r = client.get("/api/admin/audit/export")
        assert r.status_code == 401

    def test_csv_export_returns_csv(self, client, auth):
        r = client.get("/api/admin/audit/export", headers=auth)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert "audit-log.csv" in r.headers.get("content-disposition", "")
        lines = r.text.strip().splitlines()
        assert lines[0].startswith("timestamp,actor_email")

    def test_resilience_missing_actor(self, client, auth, tenant_headers, tenant):
        """Audit log entry for auth.login_failed has no actor — endpoint must not crash."""
        client.post("/api/auth/login", data={
            "username": "noactor@audit.test", "password": "wrongpass"
        })
        r = client.get("/api/admin/audit?action=auth.login_failed", headers=auth)
        assert r.status_code == 200
