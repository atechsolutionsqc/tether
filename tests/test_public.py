"""
test_public.py — Public endpoints that require no authentication.

Covers:
  - Frontend SPA served at /
  - Static assets served
  - /api/public/branding returns tenant branding
  - Branding returns MSP defaults at root domain
  - Branding returns tenant customisation at subdomain
  - /api/public/demo returns enabled:false in non-demo mode
"""


class TestFrontend:
    def test_root_serves_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "<html" in r.text.lower()

    def test_static_css_served(self, client):
        r = client.get("/static/css/style.css")
        assert r.status_code == 200
        assert "text/css" in r.headers["content-type"]

    def test_static_js_served(self, client):
        r = client.get("/static/js/app.js")
        assert r.status_code == 200

    def test_nonexistent_static_returns_404(self, client):
        r = client.get("/static/js/doesnotexist.js")
        assert r.status_code == 404


class TestBranding:
    def test_root_domain_branding(self, client):
        r = client.get("/api/public/branding",
                       headers={"host": "localhost"})
        assert r.status_code == 200
        data = r.json()
        assert "name"         in data
        assert "accent_color" in data
        assert "is_tenant"    in data
        assert data["is_tenant"] is False

    def test_tenant_subdomain_branding(self, client, tenant):
        r = client.get("/api/public/branding",
                       headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 200
        data = r.json()
        assert data["is_tenant"]  is True
        assert data["name"]       == tenant["name"]

    def test_unknown_subdomain_falls_back_gracefully(self, client):
        r = client.get("/api/public/branding",
                       headers={"host": "unknownslug.localhost"})
        # Should return 200 with default branding, not crash
        assert r.status_code == 200


class TestStandaloneBranding:
    def test_standalone_root_returns_tenant_branding(self, client, tenant, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "standalone")
        r = client.get("/api/public/branding", headers={"host": "localhost"})
        assert r.status_code == 200
        data = r.json()
        assert data["is_tenant"]  is True
        assert data["standalone"] is True
        assert "name"         in data
        assert "accent_color" in data

    def test_non_standalone_root_returns_msp_branding(self, client, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "selfhosted")
        r = client.get("/api/public/branding", headers={"host": "localhost"})
        assert r.status_code == 200
        assert r.json()["is_tenant"] is False


class TestDemoEndpoint:
    def test_disabled_in_non_demo_mode(self, client):
        r = client.get("/api/public/demo")
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_no_credentials_exposed_in_non_demo_mode(self, client):
        data = client.get("/api/public/demo").json()
        assert "client" not in data
        assert "msp"    not in data

    def test_demo_mode_returns_credentials(self, client, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "demo")
        monkeypatch.setenv("RESET_SECRET",    "test-reset-secret")
        r = client.get("/api/public/demo")
        assert r.status_code == 200
        data = r.json()
        assert data["enabled"]          is True
        assert "email"    in data["client"]
        assert "password" in data["client"]
        assert "slug"     in data["client"]
        assert "email"    in data["msp"]
        assert "password" in data["msp"]


class TestHealth:
    def test_health_returns_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "database" in data
        assert "version" in data
        assert "deployment_mode" in data

    def test_health_no_auth_required(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200


class TestSwaggerDocs:
    def test_swagger_ui_available(self, client):
        r = client.get("/docs")
        assert r.status_code == 200
        assert "swagger" in r.text.lower()

    def test_openapi_schema_available(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        data = r.json()
        assert "paths" in data
        assert "info"  in data
