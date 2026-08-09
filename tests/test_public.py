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


class TestSettingsEmailBranding:
    def test_get_settings_includes_email_branding_fields(self, client, tenant_headers):
        r = client.get("/api/settings", headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        for field in ("email_from_name", "email_from_address",
                      "email_logo_url", "email_accent_color"):
            assert field in data, f"Missing field: {field}"

    def test_put_settings_saves_email_branding(self, client, tenant_headers, tenant):
        payload = {
            "name":               tenant["name"],
            "currency":           tenant.get("currency", "CAD"),
            "logo_url":           "",
            "accent_color":       "#d4f034",
            "email_from_name":    "Acme IT",
            "email_from_address": "it@acme.com",
            "email_logo_url":     "https://acme.com/logo.png",
            "email_accent_color": "#ff5500",
        }
        r = client.put("/api/settings", json=payload, headers=tenant_headers)
        assert r.status_code == 200

        r2 = client.get("/api/settings", headers=tenant_headers)
        assert r2.status_code == 200
        data = r2.json()
        assert data["email_from_name"]    == "Acme IT"
        assert data["email_from_address"] == "it@acme.com"
        assert data["email_logo_url"]     == "https://acme.com/logo.png"
        assert data["email_accent_color"] == "#ff5500"

    def test_put_settings_clears_email_branding_with_empty_values(self, client, tenant_headers, tenant):
        # First set some values
        client.put("/api/settings", json={
            "name": tenant["name"], "currency": "CAD",
            "logo_url": "", "accent_color": "#d4f034",
            "email_from_name": "Some Brand",
        }, headers=tenant_headers)

        # Then clear them
        r = client.put("/api/settings", json={
            "name": tenant["name"], "currency": "CAD",
            "logo_url": "", "accent_color": "#d4f034",
            "email_from_name": None,
        }, headers=tenant_headers)
        assert r.status_code == 200

        r2 = client.get("/api/settings", headers=tenant_headers)
        assert r2.json()["email_from_name"] == ""


class TestClientViewerPortal:
    """client_viewer role gets a valid token and can hit the API endpoints the portal uses."""

    def _create_viewer(self, client, auth, tenant, roles):
        import time
        uid = int(time.time() * 1000) % 999999
        email = f"viewer{uid}@fixture.com"
        viewer_role = roles.get("client_viewer")
        assert viewer_role, "client_viewer role not found"
        r = client.post("/api/users", json={
            "name":      "Portal Viewer",
            "email":     email,
            "password":  "viewerpass123",
            "role_id":   viewer_role["id"],
            "tenant_id": tenant["id"],
        }, headers=auth)
        assert r.status_code == 200, f"Viewer creation failed: {r.text}"
        return email

    def test_client_viewer_login_returns_valid_token(self, client, auth, tenant, roles):
        email = self._create_viewer(client, auth, tenant, roles)
        r = client.post("/api/auth/login",
                        data={"username": email, "password": "viewerpass123"},
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["access_token"]

    def test_client_viewer_can_access_assets(self, client, auth, tenant, roles):
        email = self._create_viewer(client, auth, tenant, roles)
        login = client.post("/api/auth/login",
                            data={"username": email, "password": "viewerpass123"},
                            headers={"host": f"{tenant['slug']}.localhost"})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}",
                   "host": f"{tenant['slug']}.localhost"}

        r = client.get("/api/assets", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data or isinstance(data, list)

    def test_client_viewer_can_access_requests(self, client, auth, tenant, roles):
        email = self._create_viewer(client, auth, tenant, roles)
        login = client.post("/api/auth/login",
                            data={"username": email, "password": "viewerpass123"},
                            headers={"host": f"{tenant['slug']}.localhost"})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}",
                   "host": f"{tenant['slug']}.localhost"}

        r = client.get("/api/requests", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestAssetTagPrefix:
    def _base_payload(self, tenant):
        return {"name": tenant["name"], "currency": "USD",
                "logo_url": "", "accent_color": "#d4f034"}

    def test_settings_includes_asset_tag_prefix_field(self, client, tenant_headers):
        r = client.get("/api/settings", headers=tenant_headers)
        assert r.status_code == 200
        assert "asset_tag_prefix" in r.json()

    def test_set_and_retrieve_prefix(self, client, tenant_headers, tenant):
        payload = {**self._base_payload(tenant), "asset_tag_prefix": "acme-"}
        r = client.put("/api/settings", json=payload, headers=tenant_headers)
        assert r.status_code == 200
        r2 = client.get("/api/settings", headers=tenant_headers)
        assert r2.json()["asset_tag_prefix"] == "ACME-"

    def test_prefix_uppercased_on_save(self, client, tenant_headers, tenant):
        payload = {**self._base_payload(tenant), "asset_tag_prefix": "org-"}
        client.put("/api/settings", json=payload, headers=tenant_headers)
        r = client.get("/api/settings", headers=tenant_headers)
        assert r.json()["asset_tag_prefix"] == "ORG-"

    def test_clear_prefix_with_empty_string(self, client, tenant_headers, tenant):
        client.put("/api/settings", json={**self._base_payload(tenant), "asset_tag_prefix": "ACME-"}, headers=tenant_headers)
        client.put("/api/settings", json={**self._base_payload(tenant), "asset_tag_prefix": ""}, headers=tenant_headers)
        r = client.get("/api/settings", headers=tenant_headers)
        assert r.json()["asset_tag_prefix"] == ""
