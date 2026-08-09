"""
conftest.py — Shared pytest fixtures for Tether's test suite.

Every test gets:
  - client    : FastAPI TestClient with a fresh SQLite database
  - auth      : MSP admin Authorization header
  - tenant    : A pre-created client tenant
  - auth_h(t) : Auth header scoped to a specific tenant host

The database is created fresh once per session in a temp directory.
No MariaDB needed — SQLite is used automatically when DB_HOST is unset.
"""
import os
import sys
import tempfile
import pytest

# ── Environment must be set BEFORE importing the app ──────────────────────────
_tmp = tempfile.mkdtemp()
os.environ.setdefault("TETHER_DATA",        _tmp)
os.environ.setdefault("EMAIL_PROVIDER",     "none")
os.environ.setdefault("DEPLOYMENT_MODE",    "selfhosted")
os.environ.setdefault("SECRET_KEY",         "test-secret-key-not-for-production")
os.environ.setdefault("BASE_DOMAIN",        "localhost")
os.environ.setdefault("APP_URL",            "http://localhost:8000")
os.environ.setdefault("ALLOW_SIGNUP",       "true")
os.environ.setdefault("STRIPE_SECRET_KEY",  "")   # disabled in tests

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient
from main import app  # noqa: E402 — must come after env setup


# ── Primary fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    """One TestClient for the whole session — database is shared across tests."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    """
    MSP admin Bearer token header.
    The admin account is seeded at startup by init_db().
    """
    r = client.post("/api/auth/login",
                    data={"username": "admin@usetether.ca", "password": "admin"})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def tenant(client, auth):
    """
    A pre-created client tenant used by asset/user tests.
    Created once per session.
    """
    r = client.post("/api/tenants", json={
        "name":     "Fixture Corp",
        "slug":     "fixture",
        "currency": "CAD",
    }, headers=auth)
    assert r.status_code == 200, f"Tenant creation failed: {r.text}"
    return r.json()


@pytest.fixture(scope="session")
def tenant_headers(auth, tenant):
    """Auth header with Host set to the fixture tenant's subdomain."""
    return {**auth, "host": f"{tenant['slug']}.localhost"}


@pytest.fixture(scope="session")
def roles(client, auth):
    """All available roles, keyed by name."""
    r = client.get("/api/users/roles/all", headers=auth)
    assert r.status_code == 200
    return {role["name"]: role for role in r.json()}


# ── Rate limiter reset ────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def reset_rate_limiters():
    """Clear in-memory rate limit stores before each test to prevent bleed."""
    # Reset login attempts
    try:
        from routers.auth import _login_attempts
        _login_attempts.clear()
    except ImportError:
        pass
    # Reset password reset attempts
    try:
        from routers.password_reset import _reset_attempts
        _reset_attempts.clear()
    except ImportError:
        pass
    # Reset signup attempts
    try:
        from routers.signup import _signup_attempts
        _signup_attempts.clear()
    except ImportError:
        pass
    yield


# ── Helper fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def fresh_asset(client, tenant_headers, tenant):
    """
    Creates a single asset and returns it.
    Unique tag per call using the fixture's own id.
    """
    import time
    tag = f"FX-{int(time.time() * 1000) % 999999:06d}"
    r = client.post("/api/assets", json={
        "asset_tag": tag,
        "name":      "Fixture Asset",
        "status":    "available",
    }, headers=tenant_headers)
    assert r.status_code == 200, f"Asset creation failed: {r.text}"
    return r.json()


@pytest.fixture
def fresh_employee(client, tenant_headers):
    """Creates an employee record and returns it."""
    import time
    uid = int(time.time() * 1000) % 999999
    r = client.post("/api/employees", json={
        "name":       f"Test Person {uid}",
        "email":      f"person{uid}@fixture.com",
        "department": "Testing",
    }, headers=tenant_headers)
    assert r.status_code == 200, f"Employee creation failed: {r.text}"
    return r.json()
