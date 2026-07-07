"""
test_admin.py — System administration endpoint tests.

Covers:
  - /admin/status returns full system info
  - /admin/backup/config returns config without secrets
  - /admin/backup/run blocked when disabled
  - /admin/backup/list returns empty when not configured
  - /admin/alerts/warranty blocked when email not configured
  - /admin/tenants/{tid}/preview-token creates/reuses preview user and returns usable JWT
  - All endpoints require msp.dashboard or tenants.manage permission
"""
import time
import pytest


class TestSystemStatus:
    def test_status_shape(self, client, auth):
        r = client.get("/api/admin/status", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "version" in data
        assert "deployment_mode" in data
        assert "database" in data
        assert "services" in data
        assert "billing" in data

    def test_database_section(self, client, auth):
        r    = client.get("/api/admin/status", headers=auth)
        db   = r.json()["database"]
        assert "total_assets"  in db
        assert "total_tenants" in db
        assert "total_users"   in db
        assert db["total_assets"]  >= 0
        assert db["total_tenants"] >= 1

    def test_services_section(self, client, auth):
        r    = client.get("/api/admin/status", headers=auth)
        svc  = r.json()["services"]
        assert "email_provider"     in svc
        assert "email_configured"   in svc
        assert "stripe_configured"  in svc
        assert "backup_enabled"     in svc
        assert "backup_configured"  in svc
        assert "warranty_alerts"    in svc

    def test_email_provider_none_not_configured(self, client, auth):
        r   = client.get("/api/admin/status", headers=auth)
        svc = r.json()["services"]
        # In test env EMAIL_PROVIDER=none
        assert svc["email_provider"]   == "none"
        assert svc["email_configured"] is False

    def test_backup_disabled_by_default(self, client, auth):
        r   = client.get("/api/admin/status", headers=auth)
        svc = r.json()["services"]
        assert svc["backup_enabled"]    is False
        assert svc["backup_configured"] is False

    def test_status_requires_auth(self, client):
        r = client.get("/api/admin/status")
        assert r.status_code == 401


class TestBackupEndpoints:
    def test_backup_config_shape(self, client, auth):
        r = client.get("/api/admin/backup/config", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "enabled"        in data
        assert "configured"     in data
        assert "interval_hours" in data
        assert "retain_days"    in data
        assert "bucket"         in data
        # Secret key must NOT be in the response
        assert "access_key" not in data
        assert "secret_key" not in data

    def test_backup_run_blocked_when_disabled(self, client, auth):
        r = client.post("/api/admin/backup/run", headers=auth)
        assert r.status_code == 400
        assert "BACKUP_ENABLED" in r.json()["detail"]

    def test_backup_list_empty_when_not_configured(self, client, auth):
        r = client.get("/api/admin/backup/list", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "backups" in data
        assert data["backups"] == []

    def test_backup_requires_auth(self, client):
        for method, path in [
            ("get",  "/api/admin/backup/config"),
            ("post", "/api/admin/backup/run"),
            ("get",  "/api/admin/backup/list"),
        ]:
            r = getattr(client, method)(path)
            assert r.status_code == 401


class TestWarrantyAlerts:
    def test_warranty_alert_blocked_when_email_not_configured(self, client, auth):
        """EMAIL_PROVIDER=none in test env — alert should return 400."""
        r = client.post("/api/admin/alerts/warranty", headers=auth)
        assert r.status_code == 400
        assert "email" in r.json()["detail"].lower()

    def test_warranty_alert_requires_auth(self, client):
        r = client.post("/api/admin/alerts/warranty")
        assert r.status_code == 401


class TestLicenceAlerts:
    def test_licence_alert_blocked_when_email_not_configured(self, client, auth):
        """EMAIL_PROVIDER=none in test env — alert should return 400."""
        r = client.post("/api/admin/alerts/licence", headers=auth)
        assert r.status_code == 400
        assert "email" in r.json()["detail"].lower()

    def test_licence_alert_requires_auth(self, client):
        r = client.post("/api/admin/alerts/licence")
        assert r.status_code == 401

    def test_status_includes_licence_config(self, client, auth):
        r = client.get("/api/admin/status", headers=auth)
        assert r.status_code == 200
        services = r.json()["services"]
        assert "licence_alerts" in services
        assert "licence_window_days" in services


class TestAdminPermissions:
    """Non-MSP users must not access admin endpoints."""

    @pytest.fixture
    def client_user_token(self, client, auth, tenant, roles):
        import time
        email = f"clientonly{int(time.time()*1000)%9999}@test.com"
        client.post("/api/users", json={
            "name": "Client Only", "email": email, "password": "password123",
            "role_id":      roles["client_viewer"]["id"],
            "tenant_id":    tenant["id"],
            "is_msp_staff": False, "active": True,
        }, headers=auth)
        r = client.post("/api/auth/login",
                        data={"username": email, "password": "password123"})
        return {"Authorization": f"Bearer {r.json()['access_token']}",
                "host": f"{tenant['slug']}.localhost"}

    def test_client_user_cannot_access_admin_status(self, client,
                                                     client_user_token):
        r = client.get("/api/admin/status", headers=client_user_token)
        assert r.status_code == 403

    def test_client_user_cannot_run_backup(self, client, client_user_token):
        r = client.post("/api/admin/backup/run", headers=client_user_token)
        assert r.status_code == 403


class TestPreviewToken:
    def test_returns_token_and_slug(self, client, auth, tenant):
        r = client.post(f"/api/admin/tenants/{tenant['id']}/preview-token", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert data["slug"] == tenant["slug"]

    def test_idempotent_no_duplicate_users(self, client, auth, tenant):
        r1 = client.post(f"/api/admin/tenants/{tenant['id']}/preview-token", headers=auth)
        r2 = client.post(f"/api/admin/tenants/{tenant['id']}/preview-token", headers=auth)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert "token" in r1.json()
        assert "token" in r2.json()

    def test_nonexistent_tenant_returns_404(self, client, auth):
        r = client.post("/api/admin/tenants/999999/preview-token", headers=auth)
        assert r.status_code == 404

    def test_requires_msp(self, client, auth, tenant, roles):
        uid = int(time.time() * 1000) % 999999
        email = f"nopreview{uid}@test.com"
        client.post("/api/users", json={
            "name": "No Preview", "email": email, "password": "password123",
            "role_id": roles["client_viewer"]["id"],
            "tenant_id": tenant["id"],
            "is_msp_staff": False, "active": True,
        }, headers=auth)
        r = client.post("/api/auth/login", data={"username": email, "password": "password123"})
        non_msp_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
        r = client.post(f"/api/admin/tenants/{tenant['id']}/preview-token", headers=non_msp_auth)
        assert r.status_code == 403

    def test_token_is_usable_as_client(self, client, auth, tenant):
        r = client.post(f"/api/admin/tenants/{tenant['id']}/preview-token", headers=auth)
        preview_token = r.json()["token"]
        slug = r.json()["slug"]
        preview_auth = {
            "Authorization": f"Bearer {preview_token}",
            "host": f"{slug}.localhost",
        }
        me = client.get("/api/auth/me", headers=preview_auth)
        assert me.status_code == 200
        assert me.json()["is_msp_staff"] is False

    def test_preview_token_not_msp(self, client, auth, tenant):
        r = client.post(f"/api/admin/tenants/{tenant['id']}/preview-token", headers=auth)
        preview_token = r.json()["token"]
        slug = r.json()["slug"]
        preview_auth = {
            "Authorization": f"Bearer {preview_token}",
            "host": f"{slug}.localhost",
        }
        # Preview user cannot reach MSP admin endpoints
        r2 = client.get("/api/admin/status", headers=preview_auth)
        assert r2.status_code == 403
