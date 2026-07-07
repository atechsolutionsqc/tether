"""
test_locations.py — Location management tests.

Covers:
  - Create / list / update / delete
  - Duplicate name rejection
  - 404 on missing resource
  - Delete blocked when assets are assigned
  - Authentication required
"""
import time


def _name():
    return f"Loc-{int(time.time() * 1000) % 999999:06d}"


def _tag():
    return f"LX-{int(time.time() * 1000) % 999999:06d}"


class TestCreateLocation:
    def test_create(self, client, tenant_headers):
        r = client.post("/api/locations", json={"name": _name(), "address": "123 Main St"}, headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["address"] == "123 Main St"
        assert data["asset_count"] == 0

    def test_default_address_is_empty(self, client, tenant_headers):
        r = client.post("/api/locations", json={"name": _name()}, headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["address"] == ""

    def test_duplicate_name_rejected(self, client, tenant_headers):
        name = _name()
        client.post("/api/locations", json={"name": name}, headers=tenant_headers)
        r = client.post("/api/locations", json={"name": name}, headers=tenant_headers)
        assert r.status_code == 400

    def test_requires_authentication(self, client, tenant):
        r = client.post("/api/locations", json={"name": _name()},
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestListLocations:
    def test_list_returns_list(self, client, tenant_headers):
        r = client.get("/api/locations", headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_created_location_appears(self, client, tenant_headers):
        name = _name()
        client.post("/api/locations", json={"name": name}, headers=tenant_headers)
        r = client.get("/api/locations", headers=tenant_headers)
        assert r.status_code == 200
        names = [l["name"] for l in r.json()["items"]]
        assert name in names

    def test_requires_authentication(self, client, tenant):
        r = client.get("/api/locations", headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestUpdateLocation:
    def test_update_name_and_address(self, client, tenant_headers):
        loc = client.post("/api/locations", json={"name": _name()}, headers=tenant_headers).json()
        new_name = _name()
        r = client.put(f"/api/locations/{loc['id']}",
                       json={"name": new_name, "address": "456 New Ave"}, headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == new_name
        assert data["address"] == "456 New Ave"

    def test_update_not_found(self, client, tenant_headers):
        r = client.put("/api/locations/999999", json={"name": "X"}, headers=tenant_headers)
        assert r.status_code == 404


class TestDeleteLocation:
    def test_delete(self, client, tenant_headers):
        loc = client.post("/api/locations", json={"name": _name()}, headers=tenant_headers).json()
        r = client.delete(f"/api/locations/{loc['id']}", headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete_not_found(self, client, tenant_headers):
        r = client.delete("/api/locations/999999", headers=tenant_headers)
        assert r.status_code == 404

    def test_delete_blocked_when_assets_assigned(self, client, tenant_headers):
        loc = client.post("/api/locations", json={"name": _name()}, headers=tenant_headers).json()
        client.post("/api/assets", json={
            "asset_tag": _tag(), "name": "Linked Asset", "status": "available",
            "location_id": loc["id"],
        }, headers=tenant_headers)
        r = client.delete(f"/api/locations/{loc['id']}", headers=tenant_headers)
        assert r.status_code == 400
