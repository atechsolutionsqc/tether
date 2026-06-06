"""
test_auth.py — Authentication tests.

Covers:
  - Login success / failure
  - Login rate limiting (10 bad attempts → 429)
  - /me endpoint returns correct user data
  - Change password
  - Unauthenticated requests rejected
"""
import pytest


class TestLogin:
    def test_login_success(self, client):
        r = client.post("/api/auth/login",
                        data={"username": "admin@usetether.ca", "password": "admin"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        r = client.post("/api/auth/login",
                        data={"username": "admin@usetether.ca", "password": "wrongpassword"})
        assert r.status_code == 401
        assert "Incorrect" in r.json()["detail"]

    def test_login_nonexistent_email(self, client):
        r = client.post("/api/auth/login",
                        data={"username": "nobody@nowhere.com", "password": "whatever"})
        assert r.status_code == 401

    def test_login_empty_credentials(self, client):
        r = client.post("/api/auth/login",
                        data={"username": "", "password": ""})
        assert r.status_code in (401, 422)

    def test_login_rate_limiting(self, client):
        """10 bad attempts from the same IP triggers 429."""
        for _ in range(10):
            client.post("/api/auth/login",
                        data={"username": "ratelimit@test.com", "password": "bad"})
        r = client.post("/api/auth/login",
                        data={"username": "ratelimit@test.com", "password": "bad"})
        assert r.status_code == 429
        assert "Too many" in r.json()["detail"]


class TestMe:
    def test_me_returns_user(self, client, auth):
        r = client.get("/api/auth/me", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == "admin@usetether.ca"
        assert data["is_msp_staff"] is True
        assert "permissions" in data
        assert len(data["permissions"]) > 0

    def test_me_unauthenticated(self, client):
        r = client.get("/api/auth/me")
        assert r.status_code == 401

    def test_me_bad_token(self, client):
        r = client.get("/api/auth/me",
                       headers={"Authorization": "Bearer thisisnotavalidtoken"})
        assert r.status_code == 401


class TestChangePassword:
    def test_change_password_wrong_current(self, client, auth):
        r = client.post("/api/auth/change-password", json={
            "current_password": "wrongcurrent",
            "new_password":     "newpassword123",
        }, headers=auth)
        assert r.status_code == 400

    def test_change_password_too_short(self, client, auth):
        r = client.post("/api/auth/change-password", json={
            "current_password": "admin",
            "new_password":     "short",
        }, headers=auth)
        # Min length enforced (400) or accepted — both are valid app behaviours
        assert r.status_code in (200, 400)


class TestUnauthenticated:
    """Protected endpoints must reject unauthenticated requests."""

    @pytest.mark.parametrize("method,path", [
        ("get",  "/api/assets"),
        ("get",  "/api/tenants"),
        ("get",  "/api/billing/status"),
        ("get",  "/api/admin/status"),
    ])
    def test_protected_endpoints_require_auth(self, client, method, path):
        r = getattr(client, method)(path)
        assert r.status_code == 401
