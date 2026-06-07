"""
test_reports.py - Reports endpoint coverage.

Covers:
  - Response shape and key fields
  - Warranty day filtering
  - Auth requirements
  - Tenant scoping for client users
  - MSP aggregate by-tenant visibility
  - CSV export content type
"""

import time
from datetime import date, timedelta


def _uid() -> int:
    return int(time.time() * 1000) % 99999999


def _create_tenant(client, auth, slug_prefix: str):
    u = _uid()
    return client.post(
        "/api/tenants",
        json={"name": f"{slug_prefix} {u}", "slug": f"{slug_prefix}{u}", "currency": "CAD"},
        headers=auth,
    ).json()


def _tenant_headers(auth, slug: str):
    return {**auth, "host": f"{slug}.localhost"}


def _create_asset(client, headers, tag: str, **overrides):
    payload = {
        "asset_tag": tag,
        "name": f"Asset {tag}",
        "status": "available",
    }
    payload.update(overrides)
    r = client.post("/api/assets", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _create_client_viewer_and_login(client, auth, tenant, roles):
    email = f"viewer{_uid()}@test.com"
    r = client.post(
        "/api/users",
        json={
            "name": "Reports Viewer",
            "email": email,
            "password": "password123",
            "role_id": roles["client_viewer"]["id"],
            "tenant_id": tenant["id"],
            "is_msp_staff": False,
            "active": True,
        },
        headers=auth,
    )
    assert r.status_code == 200, r.text

    lr = client.post("/api/auth/login", data={"username": email, "password": "password123"})
    assert lr.status_code == 200, lr.text
    token = lr.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "host": f"{tenant['slug']}.localhost"}


class TestReportsEndpoints:
    def test_warranty_returns_expected_shape(self, client, auth, tenant):
        headers = _tenant_headers(auth, tenant["slug"])
        exp = (date.today() + timedelta(days=20)).isoformat()
        tag = f"RPT-W-{_uid()}"
        _create_asset(
            client,
            headers,
            tag,
            manufacturer="Dell",
            warranty_expiry=exp,
            purchase_cost=1299.99,
        )

        r = client.get("/api/reports/warranty?days=30", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        row = next((x for x in data if x["asset_tag"] == tag), None)
        assert row is not None
        for key in [
            "asset_tag",
            "name",
            "manufacturer",
            "warranty_expiry",
            "days_remaining",
            "tenant_name",
            "location_name",
            "assigned_to_name",
            "purchase_cost",
        ]:
            assert key in row

    def test_warranty_respects_days_query(self, client, auth, tenant):
        headers = _tenant_headers(auth, tenant["slug"])
        near_tag = f"RPT-N-{_uid()}"
        far_tag = f"RPT-F-{_uid()}"
        _create_asset(
            client,
            headers,
            near_tag,
            warranty_expiry=(date.today() + timedelta(days=10)).isoformat(),
        )
        _create_asset(
            client,
            headers,
            far_tag,
            warranty_expiry=(date.today() + timedelta(days=120)).isoformat(),
        )

        d30 = client.get("/api/reports/warranty?days=30", headers=headers)
        assert d30.status_code == 200
        tags30 = {x["asset_tag"] for x in d30.json()}
        assert near_tag in tags30
        assert far_tag not in tags30

        d180 = client.get("/api/reports/warranty?days=180", headers=headers)
        assert d180.status_code == 200
        tags180 = {x["asset_tag"] for x in d180.json()}
        assert near_tag in tags180
        assert far_tag in tags180

    def test_assets_by_status_summary_keys(self, client, auth, tenant):
        headers = _tenant_headers(auth, tenant["slug"])
        r = client.get("/api/reports/assets-by-status", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        for key in ["available", "deployed", "maintenance", "retired", "total"]:
            assert key in data["summary"]

    def test_value_total_value_is_number(self, client, auth, tenant):
        headers = _tenant_headers(auth, tenant["slug"])
        _create_asset(client, headers, f"RPT-V-{_uid()}", purchase_cost=500.25)
        r = client.get("/api/reports/value", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_value" in data
        assert isinstance(data["total_value"], (int, float))

    def test_export_returns_csv_content_type(self, client, auth, tenant):
        headers = _tenant_headers(auth, tenant["slug"])
        r = client.get("/api/reports/export?report_type=assets", headers=headers)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/csv")
        assert "attachment; filename=tether-report-assets-" in r.headers.get(
            "content-disposition", ""
        )

    def test_all_reports_endpoints_require_auth(self, client, tenant):
        host = {"host": f"{tenant['slug']}.localhost"}
        urls = [
            "/api/reports/warranty",
            "/api/reports/assets-by-status",
            "/api/reports/value",
            "/api/reports/export?report_type=assets",
        ]
        for u in urls:
            r = client.get(u, headers=host)
            assert r.status_code == 401

    def test_client_viewer_can_access_reports(self, client, auth, tenant, roles):
        viewer_headers = _create_client_viewer_and_login(client, auth, tenant, roles)
        endpoints = [
            "/api/reports/warranty",
            "/api/reports/assets-by-status",
            "/api/reports/value",
            "/api/reports/export?report_type=warranty&days=30",
        ]
        for u in endpoints:
            r = client.get(u, headers=viewer_headers)
            assert r.status_code == 200, f"{u} failed with {r.status_code}: {r.text}"

    def test_client_viewer_only_sees_own_tenant_data(self, client, auth, tenant, roles):
        other = _create_tenant(client, auth, "rptiso")
        own_h = _tenant_headers(auth, tenant["slug"])
        oth_h = _tenant_headers(auth, other["slug"])

        own_tag = f"RPT-OWN-{_uid()}"
        other_tag = f"RPT-OTH-{_uid()}"
        _create_asset(
            client,
            own_h,
            own_tag,
            purchase_cost=111.0,
            warranty_expiry=(date.today() + timedelta(days=15)).isoformat(),
        )
        _create_asset(
            client,
            oth_h,
            other_tag,
            purchase_cost=9999.0,
            warranty_expiry=(date.today() + timedelta(days=15)).isoformat(),
        )

        viewer_headers = _create_client_viewer_and_login(client, auth, tenant, roles)

        wr = client.get("/api/reports/warranty?days=30", headers=viewer_headers)
        assert wr.status_code == 200
        wtags = {x["asset_tag"] for x in wr.json()}
        assert own_tag in wtags
        assert other_tag not in wtags

        ar = client.get("/api/reports/assets-by-status", headers=viewer_headers)
        assert ar.status_code == 200
        assert "by_tenant" not in ar.json()

        vr = client.get("/api/reports/value", headers=viewer_headers)
        assert vr.status_code == 200
        v = vr.json()
        assert "by_tenant" not in v
        top_tags = {x["asset_tag"] for x in v.get("top_assets", [])}
        assert other_tag not in top_tags

    def test_msp_admin_sees_by_tenant_fields(self, client, auth):
        t1 = _create_tenant(client, auth, "rptmspa")
        t2 = _create_tenant(client, auth, "rptmspb")
        _create_asset(
            client,
            _tenant_headers(auth, t1["slug"]),
            f"RPT-M1-{_uid()}",
            purchase_cost=222.0,
        )
        _create_asset(
            client,
            _tenant_headers(auth, t2["slug"]),
            f"RPT-M2-{_uid()}",
            purchase_cost=333.0,
        )

        rs = client.get("/api/reports/assets-by-status", headers=auth)
        assert rs.status_code == 200
        status_data = rs.json()
        assert "by_tenant" in status_data
        tenant_names = {x["tenant_name"] for x in status_data["by_tenant"]}
        assert t1["name"] in tenant_names
        assert t2["name"] in tenant_names

        rv = client.get("/api/reports/value", headers=auth)
        assert rv.status_code == 200
        value_data = rv.json()
        assert "by_tenant" in value_data
        tenant_names_v = {x["tenant_name"] for x in value_data["by_tenant"]}
        assert t1["name"] in tenant_names_v
        assert t2["name"] in tenant_names_v
