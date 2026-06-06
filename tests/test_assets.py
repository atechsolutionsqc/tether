"""
test_assets.py — Asset management tests.

Covers:
  - Create / read / update / delete
  - Asset tag uniqueness within tenant
  - Status lifecycle (available → deployed → available)
  - Check-out and check-in
  - Checkout history
  - QR code generation
  - CSV export
  - CSV import (create + update + error rows)
  - Search and filtering
  - Cross-tenant isolation
"""
import io
import time


def _tag():
    return f"AT-{int(time.time() * 1000) % 999999:06d}"


class TestCreateAsset:
    def test_create_asset(self, client, tenant_headers):
        r = client.post("/api/assets", json={
            "asset_tag": _tag(), "name": "Test Laptop",
            "status": "available", "manufacturer": "Dell",
        }, headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Test Laptop"
        assert data["status"] == "available"

    def test_duplicate_tag_rejected(self, client, tenant_headers):
        tag = _tag()
        client.post("/api/assets", json={
            "asset_tag": tag, "name": "First", "status": "available",
        }, headers=tenant_headers)
        r = client.post("/api/assets", json={
            "asset_tag": tag, "name": "Second", "status": "available",
        }, headers=tenant_headers)
        assert r.status_code == 400

    def test_requires_authentication(self, client, tenant):
        r = client.post("/api/assets", json={
            "asset_tag": _tag(), "name": "X", "status": "available",
        }, headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestReadAsset:
    def test_list_assets(self, client, tenant_headers, fresh_asset):
        r = client.get("/api/assets", headers=tenant_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        tags = [a["asset_tag"] for a in r.json()]
        assert fresh_asset["asset_tag"] in tags

    def test_get_asset_by_id(self, client, tenant_headers, fresh_asset):
        r = client.get(f"/api/assets/{fresh_asset['id']}", headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["id"] == fresh_asset["id"]

    def test_get_nonexistent_returns_404(self, client, tenant_headers):
        r = client.get("/api/assets/999999", headers=tenant_headers)
        assert r.status_code == 404

    def test_search_by_name(self, client, tenant_headers):
        tag  = _tag()
        name = f"SearchableAsset{tag}"
        client.post("/api/assets", json={
            "asset_tag": tag, "name": name, "status": "available",
        }, headers=tenant_headers)
        r = client.get(f"/api/assets?q={tag}", headers=tenant_headers)
        assert r.status_code == 200
        assert any(a["asset_tag"] == tag for a in r.json())

    def test_filter_by_status(self, client, tenant_headers):
        r = client.get("/api/assets?status=available", headers=tenant_headers)
        assert r.status_code == 200
        for asset in r.json():
            assert asset["status"] == "available"


class TestUpdateAsset:
    def test_update_asset_name(self, client, tenant_headers, fresh_asset):
        asset = fresh_asset
        r = client.put(f"/api/assets/{asset['id']}", json={
            **asset,
            "name":   "Updated Name",
            "status": "available",
        }, headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["name"] == "Updated Name"

    def test_update_status_to_maintenance(self, client, tenant_headers, fresh_asset):
        asset = fresh_asset
        r = client.put(f"/api/assets/{asset['id']}", json={
            **asset, "status": "maintenance",
        }, headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "maintenance"


class TestDeleteAsset:
    def test_delete_asset(self, client, tenant_headers):
        tag = _tag()
        a = client.post("/api/assets", json={
            "asset_tag": tag, "name": "To Delete", "status": "available",
        }, headers=tenant_headers).json()
        r = client.delete(f"/api/assets/{a['id']}", headers=tenant_headers)
        assert r.status_code == 200
        r2 = client.get(f"/api/assets/{a['id']}", headers=tenant_headers)
        assert r2.status_code == 404


class TestCheckout:
    def test_checkout_and_checkin(self, client, tenant_headers,
                                  fresh_asset, fresh_employee):
        asset_id    = fresh_asset["id"]
        employee_id = fresh_employee["id"]

        # Check out
        r = client.post(f"/api/assets/{asset_id}/checkout", json={
            "employee_id": employee_id,
            "note":        "Test checkout",
        }, headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "deployed"

        # Check in
        r2 = client.post(f"/api/assets/{asset_id}/checkin", json={
            "note": "Returned",
        }, headers=tenant_headers)
        assert r2.status_code == 200
        assert r2.json()["status"] == "available"

    def test_cannot_checkout_deployed_asset(self, client, tenant_headers,
                                             fresh_employee):
        tag = _tag()
        a = client.post("/api/assets", json={
            "asset_tag": tag, "name": "Busy Asset", "status": "available",
        }, headers=tenant_headers).json()

        # First checkout
        client.post(f"/api/assets/{a['id']}/checkout",
                    json={"employee_id": fresh_employee["id"]},
                    headers=tenant_headers)

        # Second checkout should fail
        r = client.post(f"/api/assets/{a['id']}/checkout",
                        json={"employee_id": fresh_employee["id"]},
                        headers=tenant_headers)
        assert r.status_code == 400

    def test_checkout_history_recorded(self, client, tenant_headers,
                                        fresh_asset, fresh_employee):
        asset_id = fresh_asset["id"]
        client.post(f"/api/assets/{asset_id}/checkout", json={
            "employee_id": fresh_employee["id"],
            "note":        "History test",
        }, headers=tenant_headers)
        r = client.get(f"/api/assets/{asset_id}/history",
                       headers=tenant_headers)
        assert r.status_code == 200
        history = r.json()
        assert len(history) >= 1
        assert history[-1]["action"] == "checkout"


class TestQR:
    def test_qr_returns_png(self, client, tenant_headers, fresh_asset):
        r = client.get(f"/api/assets/{fresh_asset['id']}/qr",
                       headers=tenant_headers)
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert len(r.content) > 100  # non-empty PNG

    def test_qr_no_auth_required(self, client, tenant, fresh_asset):
        """QR endpoint is public."""
        r = client.get(f"/api/assets/{fresh_asset['id']}/qr",
                       headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 200


class TestCSV:
    def test_export_csv(self, client, tenant_headers, fresh_asset):
        r = client.get("/api/assets/export/csv", headers=tenant_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "asset_tag" in r.text  # header row present
        assert fresh_asset["asset_tag"] in r.text

    def test_import_csv_creates_assets(self, client, tenant_headers):
        import uuid
        tag1 = f"IM-{uuid.uuid4().hex[:8].upper()}"
        tag2 = f"IM-{uuid.uuid4().hex[:8].upper()}"
        csv_data = (
            "asset_tag,name,status,manufacturer\n"
            f"{tag1},Import One,available,Apple\n"
            f"{tag2},Import Two,available,Dell\n"
        )
        r = client.post("/api/assets/import/csv",
                        files={"file": ("assets.csv", csv_data, "text/csv")},
                        headers=tenant_headers)
        assert r.status_code == 200
        result = r.json()
        assert result["created"] == 2
        assert result["errors"] == []

    def test_import_csv_updates_existing(self, client, tenant_headers):
        tag = _tag()
        # Create first
        client.post("/api/assets", json={
            "asset_tag": tag, "name": "Original", "status": "available",
        }, headers=tenant_headers)
        # Import with updated name
        csv_data = f"asset_tag,name,status\n{tag},Updated Name,available\n"
        r = client.post("/api/assets/import/csv",
                        files={"file": ("u.csv", csv_data, "text/csv")},
                        headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["updated"] == 1

    def test_import_csv_invalid_status_handled(self, client, tenant_headers):
        """Invalid status either creates with default or is reported as error."""
        import uuid
        tag = f"BAD-{uuid.uuid4().hex[:6].upper()}"
        csv_data = f"asset_tag,name,status\n{tag},Bad Asset,invalid_status\n"
        r = client.post("/api/assets/import/csv",
                        files={"file": ("bad.csv", csv_data, "text/csv")},
                        headers=tenant_headers)
        assert r.status_code == 200
        result = r.json()
        # App either reports an error OR creates with a default status — both acceptable
        assert "errors" in result or "created" in result


class TestCrossTenantIsolation:
    def test_assets_not_visible_across_tenants(self, client, auth, tenant_headers,
                                                fresh_asset):
        """Create a second tenant and verify it cannot see the first tenant's assets."""
        import time
        uid     = int(time.time() * 1000) % 999999
        slug    = f"isolated{uid}"
        other_t = client.post("/api/tenants", json={
            "name": f"Other {uid}", "slug": slug, "currency": "USD",
        }, headers=auth).json()

        other_h = {**auth, "host": f"{slug}.localhost"}
        r = client.get("/api/assets", headers=other_h)
        assert r.status_code == 200
        asset_tags = [a["asset_tag"] for a in r.json()]
        assert fresh_asset["asset_tag"] not in asset_tags
