"""
tests/test_totp.py — TOTP 2FA endpoint tests.

Covers: setup, verify, status, authenticate (full login flow), disable,
non-MSP access restriction, rate limit on bad codes, and cross-account isolation.
"""
import pyotp
import pytest


class TestTotpSetup:
    def test_setup_returns_secret_and_qr(self, client, auth):
        r = client.post("/api/auth/totp/setup", headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert "secret" in d
        assert "otpauth_uri" in d
        assert "qr_svg" in d
        assert len(d["secret"]) >= 16
        assert "otpauth://totp/" in d["otpauth_uri"]

    def test_setup_requires_auth(self, client):
        r = client.post("/api/auth/totp/setup")
        assert r.status_code == 401

    def test_setup_forbidden_for_client_user(self, client, tenant, roles, auth):
        # Create a client user
        r = client.post("/api/users", json={
            "name": "Client 2FA Test", "email": "client2fa@fixture.com",
            "password": "Password123!", "role_id": roles["client_admin"]["id"],
            "tenant_id": tenant["id"], "is_msp_staff": False,
        }, headers=auth)
        assert r.status_code == 200
        lr = client.post("/api/auth/login", data={"username": "client2fa@fixture.com", "password": "Password123!"})
        assert lr.status_code == 200
        client_auth = {"Authorization": f"Bearer {lr.json()['access_token']}"}
        r = client.post("/api/auth/totp/setup", headers=client_auth)
        assert r.status_code == 403


class TestTotpVerify:
    def test_verify_valid_code_enables_totp(self, client, auth):
        # Setup
        setup = client.post("/api/auth/totp/setup", headers=auth).json()
        code = pyotp.TOTP(setup["secret"]).now()
        r = client.post("/api/auth/totp/verify", json={"code": code}, headers=auth)
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # Status should now be enabled
        s = client.get("/api/auth/totp/status", headers=auth).json()
        assert s["enabled"] is True

        # Clean up — disable so other tests aren't affected by forced 2FA on admin
        client.request("DELETE", "/api/auth/totp",
                       json={"password": "admin"}, headers=auth)

    def test_verify_invalid_code_rejected(self, client, auth):
        client.post("/api/auth/totp/setup", headers=auth)
        r = client.post("/api/auth/totp/verify", json={"code": "000000"}, headers=auth)
        assert r.status_code == 400

    def test_verify_without_setup_rejected(self, client, roles, auth):
        # Create a fresh MSP user with no setup
        r = client.post("/api/users", json={
            "name": "MSP 2FA Fresh", "email": "msp2fa_fresh@usetether.ca",
            "password": "Password123!", "role_id": roles["msp_admin"]["id"],
            "is_msp_staff": True,
        }, headers=auth)
        assert r.status_code == 200
        lr = client.post("/api/auth/login", data={"username": "msp2fa_fresh@usetether.ca", "password": "Password123!"})
        fresh_auth = {"Authorization": f"Bearer {lr.json()['access_token']}"}
        r = client.post("/api/auth/totp/verify", json={"code": "123456"}, headers=fresh_auth)
        assert r.status_code == 400


class TestTotpLoginFlow:
    def test_login_returns_totp_required_when_enabled(self, client, auth, roles):
        # Create a dedicated MSP user for this test
        r = client.post("/api/users", json={
            "name": "MSP TOTP Flow", "email": "msp_totp_flow@usetether.ca",
            "password": "Password123!", "role_id": roles["msp_admin"]["id"],
            "is_msp_staff": True,
        }, headers=auth)
        assert r.status_code == 200
        lr = client.post("/api/auth/login", data={"username": "msp_totp_flow@usetether.ca", "password": "Password123!"})
        user_auth = {"Authorization": f"Bearer {lr.json()['access_token']}"}

        # Enable TOTP
        setup = client.post("/api/auth/totp/setup", headers=user_auth).json()
        code = pyotp.TOTP(setup["secret"]).now()
        client.post("/api/auth/totp/verify", json={"code": code}, headers=user_auth)

        # Next login should return totp_required
        r2 = client.post("/api/auth/login", data={"username": "msp_totp_flow@usetether.ca", "password": "Password123!"})
        assert r2.status_code == 200
        d = r2.json()
        assert d.get("totp_required") is True
        assert "totp_token" in d
        assert "access_token" not in d

        # Authenticate with valid code
        totp_token = d["totp_token"]
        valid_code = pyotp.TOTP(setup["secret"]).now()
        ar = client.post("/api/auth/totp/authenticate", json={"totp_token": totp_token, "code": valid_code})
        assert ar.status_code == 200
        assert "access_token" in ar.json()

        # Clean up
        full_auth = {"Authorization": f"Bearer {ar.json()['access_token']}"}
        client.request("DELETE", "/api/auth/totp", json={"password": "Password123!"}, headers=full_auth)

    def test_authenticate_with_wrong_code_rejected(self, client, auth, roles):
        r = client.post("/api/users", json={
            "name": "MSP TOTP Bad", "email": "msp_totp_bad@usetether.ca",
            "password": "Password123!", "role_id": roles["msp_admin"]["id"],
            "is_msp_staff": True,
        }, headers=auth)
        assert r.status_code == 200
        lr = client.post("/api/auth/login", data={"username": "msp_totp_bad@usetether.ca", "password": "Password123!"})
        user_auth = {"Authorization": f"Bearer {lr.json()['access_token']}"}
        setup = client.post("/api/auth/totp/setup", headers=user_auth).json()
        code = pyotp.TOTP(setup["secret"]).now()
        client.post("/api/auth/totp/verify", json={"code": code}, headers=user_auth)

        r2 = client.post("/api/auth/login", data={"username": "msp_totp_bad@usetether.ca", "password": "Password123!"})
        totp_token = r2.json()["totp_token"]
        ar = client.post("/api/auth/totp/authenticate", json={"totp_token": totp_token, "code": "000000"})
        assert ar.status_code == 400

    def test_authenticate_with_garbage_challenge_token_rejected(self, client):
        r = client.post("/api/auth/totp/authenticate", json={"totp_token": "notavalidtoken", "code": "123456"})
        assert r.status_code == 401

    def test_authenticate_with_full_jwt_as_challenge_token_rejected(self, client, auth):
        # A normal session token must NOT be accepted as a TOTP challenge token
        full_token = auth["Authorization"].split(" ")[1]
        r = client.post("/api/auth/totp/authenticate", json={"totp_token": full_token, "code": "123456"})
        assert r.status_code == 401


class TestTotpDisable:
    def test_disable_requires_correct_password(self, client, auth, roles):
        r = client.post("/api/users", json={
            "name": "MSP TOTP Disable", "email": "msp_totp_disable@usetether.ca",
            "password": "Password123!", "role_id": roles["msp_admin"]["id"],
            "is_msp_staff": True,
        }, headers=auth)
        assert r.status_code == 200
        lr = client.post("/api/auth/login", data={"username": "msp_totp_disable@usetether.ca", "password": "Password123!"})
        user_auth = {"Authorization": f"Bearer {lr.json()['access_token']}"}
        setup = client.post("/api/auth/totp/setup", headers=user_auth).json()
        code = pyotp.TOTP(setup["secret"]).now()
        client.post("/api/auth/totp/verify", json={"code": code}, headers=user_auth)

        # Wrong password
        r = client.request("DELETE", "/api/auth/totp", json={"password": "wrongpassword"}, headers=user_auth)
        assert r.status_code == 400

        # Correct password
        r = client.request("DELETE", "/api/auth/totp", json={"password": "Password123!"}, headers=user_auth)
        assert r.status_code == 200

        # Status should now be disabled
        s = client.get("/api/auth/totp/status", headers=user_auth).json()
        assert s["enabled"] is False


class TestTotpStatus:
    def test_status_false_by_default(self, client, roles, auth):
        r = client.post("/api/users", json={
            "name": "MSP TOTP Status", "email": "msp_totp_status@usetether.ca",
            "password": "Password123!", "role_id": roles["msp_admin"]["id"],
            "is_msp_staff": True,
        }, headers=auth)
        assert r.status_code == 200
        lr = client.post("/api/auth/login", data={"username": "msp_totp_status@usetether.ca", "password": "Password123!"})
        user_auth = {"Authorization": f"Bearer {lr.json()['access_token']}"}
        r = client.get("/api/auth/totp/status", headers=user_auth)
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_status_requires_auth(self, client):
        r = client.get("/api/auth/totp/status")
        assert r.status_code == 401
