"""
test_dashboard.py — Dashboard statistics tests.

The dashboard uses a single /api/dashboard/stats endpoint that returns
different shapes based on MSP vs tenant context.
"""
import time


class TestMSPDashboard:
    """MSP staff at root domain get aggregate stats across all tenants."""

    def test_msp_dashboard_shape(self, client, auth):
        r = client.get("/api/dashboard/stats", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert data["mode"]          == "msp"
        assert "total_clients"       in data
        assert "total_assets"        in data
        assert "total_value"         in data
        assert "expiring_soon"       in data
        assert "clients"             in data

    def test_msp_dashboard_includes_tenants(self, client, auth, tenant):
        r   = client.get("/api/dashboard/stats", headers=auth)
        ids = [t["id"] for t in r.json()["clients"]]
        assert tenant["id"] in ids

    def test_msp_dashboard_requires_auth(self, client):
        r = client.get("/api/dashboard/stats")
        assert r.status_code == 401

    def test_msp_dashboard_requires_assets_view(self, client, auth,
                                                  tenant, roles):
        """A client_viewer on a specific tenant cannot see the MSP dashboard."""
        email = f"mspdash{int(time.time()*1000)%9999}@test.com"
        client.post("/api/users", json={
            "name": "View Only", "email": email, "password": "password123",
            "role_id":      roles["client_viewer"]["id"],
            "tenant_id":    tenant["id"],
            "is_msp_staff": False, "active": True,
        }, headers=auth)
        tok = client.post("/api/auth/login",
                          data={"username": email, "password": "password123"}).json()["access_token"]
        # Client viewer has assets.view but not msp.dashboard — gets tenant stats not msp
        r = client.get("/api/dashboard/stats",
                       headers={"Authorization": f"Bearer {tok}",
                                "host": f"{tenant['slug']}.localhost"})
        # Should return tenant-scoped stats (mode=tenant), not msp
        assert r.status_code == 200
        assert r.json()["mode"] != "msp"

    def test_msp_asset_count_increases(self, client, auth, tenant_headers):
        before = client.get("/api/dashboard/stats",
                            headers=auth).json()["total_assets"]
        tag = f"DSH-{int(time.time()*1000)%999999:06d}"
        client.post("/api/assets", json={
            "asset_tag": tag, "name": "Dashboard Asset", "status": "available",
        }, headers=tenant_headers)
        after = client.get("/api/dashboard/stats",
                           headers=auth).json()["total_assets"]
        assert after == before + 1


class TestTenantDashboard:
    def test_tenant_dashboard_shape(self, client, tenant_headers):
        r = client.get("/api/dashboard/stats", headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["mode"]              == "tenant"
        assert "total_assets"            in data
        assert "by_status"               in data
        assert "expiring_warranties"     in data
        assert "overdue_maintenance"     in data
        assert "upcoming_maintenance"    in data

    def test_tenant_dashboard_scoped(self, client, auth):
        """Two tenants see different stats."""
        uid   = int(time.time()*1000) % 999999
        slug1 = f"sc1{uid}"
        slug2 = f"sc2{uid}"
        t1 = client.post("/api/tenants", json={
            "name": f"S1 {uid}", "slug": slug1, "currency": "CAD",
        }, headers=auth).json()
        t2 = client.post("/api/tenants", json={
            "name": f"S2 {uid}", "slug": slug2, "currency": "CAD",
        }, headers=auth).json()
        h1 = {**auth, "host": f"{slug1}.localhost"}
        h2 = {**auth, "host": f"{slug2}.localhost"}

        # Add 3 assets to t1, 1 to t2
        for i in range(3):
            client.post("/api/assets", json={
                "asset_tag": f"T1{uid}{i}", "name": f"A{i}", "status": "available",
            }, headers=h1)
        client.post("/api/assets", json={
            "asset_tag": f"T2{uid}0", "name": "B0", "status": "available",
        }, headers=h2)

        d1 = client.get("/api/dashboard/stats", headers=h1).json()
        d2 = client.get("/api/dashboard/stats", headers=h2).json()

        assert d1["total_assets"] >= 3
        assert d2["total_assets"] >= 1
        assert d1["total_assets"] > d2["total_assets"]


class TestClientDrilldown:
    def test_drilldown_returns_full_stats(self, client, auth, tenant):
        r = client.get(f"/api/dashboard/client/{tenant['id']}", headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert d["mode"] == "tenant"
        assert "total_assets" in d
        assert "expiring_warranties" in d
        assert "recent_activity" in d
        assert "by_status" in d

    def test_drilldown_requires_msp_permission(self, client, auth, tenant, roles):
        import time as _time
        email = f"drill{int(_time.time()*1000)%9999}@test.com"
        client.post("/api/users", json={
            "name": "Drill Client", "email": email, "password": "password123",
            "role_id": roles["client_admin"]["id"], "tenant_id": tenant["id"],
            "is_msp_staff": False,
        }, headers=auth)
        tok = client.post("/api/auth/login", data={"username": email, "password": "password123"}).json()["access_token"]
        r = client.get(f"/api/dashboard/client/{tenant['id']}",
                       headers={"Authorization": f"Bearer {tok}", "host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 403

    def test_drilldown_404_for_unknown_tenant(self, client, auth):
        r = client.get("/api/dashboard/client/99999", headers=auth)
        assert r.status_code == 404

    def test_drilldown_requires_auth(self, client, tenant):
        r = client.get(f"/api/dashboard/client/{tenant['id']}")
        assert r.status_code == 401
