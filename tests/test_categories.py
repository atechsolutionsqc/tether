"""
test_categories.py — Category management tests.

Covers:
  - Create / list / update / delete
  - Duplicate name rejection
  - 404 on missing resource
  - Delete blocked when assets are assigned
  - Authentication required
"""
import time


def _name():
    return f"Cat-{int(time.time() * 1000) % 999999:06d}"


def _tag():
    return f"CX-{int(time.time() * 1000) % 999999:06d}"


class TestCreateCategory:
    def test_create(self, client, tenant_headers):
        r = client.post("/api/categories", json={"name": _name(), "icon": "laptop"}, headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["icon"] == "laptop"
        assert data["asset_count"] == 0

    def test_default_icon_is_box(self, client, tenant_headers):
        r = client.post("/api/categories", json={"name": _name()}, headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["icon"] == "box"

    def test_duplicate_name_rejected(self, client, tenant_headers):
        name = _name()
        client.post("/api/categories", json={"name": name}, headers=tenant_headers)
        r = client.post("/api/categories", json={"name": name}, headers=tenant_headers)
        assert r.status_code == 400

    def test_requires_authentication(self, client, tenant):
        r = client.post("/api/categories", json={"name": _name()},
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestListCategories:
    def test_list_returns_list(self, client, tenant_headers):
        r = client.get("/api/categories", headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_created_category_appears(self, client, tenant_headers):
        name = _name()
        client.post("/api/categories", json={"name": name}, headers=tenant_headers)
        r = client.get("/api/categories", headers=tenant_headers)
        assert r.status_code == 200
        names = [c["name"] for c in r.json()["items"]]
        assert name in names

    def test_requires_authentication(self, client, tenant):
        r = client.get("/api/categories", headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestUpdateCategory:
    def test_update_name_and_icon(self, client, tenant_headers):
        cat = client.post("/api/categories", json={"name": _name()}, headers=tenant_headers).json()
        new_name = _name()
        r = client.put(f"/api/categories/{cat['id']}",
                       json={"name": new_name, "icon": "monitor"}, headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == new_name
        assert data["icon"] == "monitor"

    def test_update_not_found(self, client, tenant_headers):
        r = client.put("/api/categories/999999", json={"name": "X"}, headers=tenant_headers)
        assert r.status_code == 404


class TestDeleteCategory:
    def test_delete(self, client, tenant_headers):
        cat = client.post("/api/categories", json={"name": _name()}, headers=tenant_headers).json()
        r = client.delete(f"/api/categories/{cat['id']}", headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete_not_found(self, client, tenant_headers):
        r = client.delete("/api/categories/999999", headers=tenant_headers)
        assert r.status_code == 404

    def test_delete_blocked_when_assets_assigned(self, client, tenant_headers):
        cat = client.post("/api/categories", json={"name": _name()}, headers=tenant_headers).json()
        client.post("/api/assets", json={
            "asset_tag": _tag(), "name": "Linked Asset", "status": "available",
            "category_id": cat["id"],
        }, headers=tenant_headers)
        r = client.delete(f"/api/categories/{cat['id']}", headers=tenant_headers)
        assert r.status_code == 400
