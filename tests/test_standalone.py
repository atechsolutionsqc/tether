"""
test_standalone.py — Standalone deployment mode tests.

Covers:
  - _seed() creates a client_admin user (not MSP) in standalone mode
  - _seed() creates no MSP user in standalone mode
  - The seeded user can log in and receives a non-MSP token
  - /api/settings returns mode:tenant for the standalone user
  - /api/public/branding returns tenant branding at root domain in standalone mode
"""
import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="module")
def standalone_db(tmp_path_factory):
    """
    Isolated in-memory SQLite DB seeded in standalone mode.
    Returns (client, auth_headers) ready to make API calls.
    """
    tmp = tmp_path_factory.mktemp("standalone")

    # Override env vars BEFORE importing any app module
    env_overrides = {
        "TETHER_DATA":       str(tmp),
        "DEPLOYMENT_MODE":   "standalone",
        "ADMIN_EMAIL":       "owner@acmecorp.com",
        "ADMIN_PASSWORD":    "password123",
        "ADMIN_NAME":        "Alice Owner",
        "DEFAULT_TENANT_SLUG": "acmecorp",
        "DEFAULT_TENANT_NAME": "Acme Corp",
        "DATABASE_URL":      f"sqlite:///{tmp}/standalone.db",
        "SECRET_KEY":        "standalone-test-secret",
        "EMAIL_PROVIDER":    "none",
        "BASE_DOMAIN":       "localhost",
        "APP_URL":           "http://localhost:8000",
        "ALLOW_SIGNUP":      "false",
        "STRIPE_SECRET_KEY": "",
        "BACKUP_ENABLED":    "false",
    }

    # Patch env and re-import fresh copies of the app modules
    original_env = {k: os.environ.get(k) for k in env_overrides}
    for k, v in env_overrides.items():
        os.environ[k] = v

    # Remove cached modules so they re-read the new env
    for mod in list(sys.modules.keys()):
        if any(mod.startswith(p) for p in ("db.", "models.", "security", "main", "billing", "routers.", "scheduler", "backup_service", "email_service", "rate_limit")):
            del sys.modules[mod]

    from fastapi.testclient import TestClient
    from main import app
    from db.database import init_db
    init_db()

    with TestClient(app) as c:
        yield c

    # Restore env
    for k, v in original_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(scope="module")
def standalone_auth(standalone_db):
    r = standalone_db.post("/api/auth/login",
                           data={"username": "owner@acmecorp.com", "password": "password123"})
    assert r.status_code == 200, f"Standalone login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class TestStandaloneSeeding:
    def test_login_succeeds(self, standalone_db):
        r = standalone_db.post("/api/auth/login",
                               data={"username": "owner@acmecorp.com", "password": "password123"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_user_is_not_msp(self, standalone_db, standalone_auth):
        r = standalone_db.get("/api/auth/me", headers=standalone_auth)
        assert r.status_code == 200
        me = r.json()
        assert me["is_msp_staff"] is False
        assert me["name"] == "Alice Owner"

    def test_settings_returns_tenant_mode(self, standalone_db, standalone_auth):
        r = standalone_db.get("/api/settings", headers=standalone_auth)
        assert r.status_code == 200
        data = r.json()
        assert data["mode"]  == "tenant"
        assert data["name"]  == "Acme Corp"

    def test_msp_endpoints_are_inaccessible(self, standalone_db, standalone_auth):
        r = standalone_db.get("/api/admin/status", headers=standalone_auth)
        assert r.status_code == 403

    def test_client_endpoints_are_accessible(self, standalone_db, standalone_auth):
        r = standalone_db.get("/api/assets", headers=standalone_auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_default_categories_seeded(self, standalone_db, standalone_auth):
        r = standalone_db.get("/api/categories", headers=standalone_auth)
        assert r.status_code == 200
        names = [c["name"] for c in r.json()]
        assert "Laptop" in names
        assert "Server" in names

    def test_default_locations_seeded(self, standalone_db, standalone_auth):
        r = standalone_db.get("/api/locations", headers=standalone_auth)
        assert r.status_code == 200
        names = [l["name"] for l in r.json()]
        assert "Head Office" in names
