"""
test_employees.py — Employee management tests.

Covers:
  - Create / list / update / delete
  - Optional fields (email, department)
  - 404 on missing resource
  - Delete blocked when assets are assigned
  - Authentication required
"""
import time


def _uid():
    return int(time.time() * 1000) % 999999


def _tag():
    return f"EX-{_uid():06d}"


class TestCreateEmployee:
    def test_create_full(self, client, tenant_headers):
        uid = _uid()
        r = client.post("/api/employees", json={
            "name": f"Alice {uid}",
            "email": f"alice{uid}@example.com",
            "department": "Engineering",
        }, headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["department"] == "Engineering"
        assert data["asset_count"] == 0

    def test_create_name_only(self, client, tenant_headers):
        r = client.post("/api/employees", json={"name": f"Bob {_uid()}"}, headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == ""
        assert data["department"] == ""

    def test_requires_authentication(self, client, tenant):
        r = client.post("/api/employees", json={"name": "Anon"},
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestListEmployees:
    def test_list_returns_list(self, client, tenant_headers):
        r = client.get("/api/employees", headers=tenant_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_created_employee_appears(self, client, tenant_headers):
        uid = _uid()
        name = f"Carol {uid}"
        client.post("/api/employees", json={"name": name}, headers=tenant_headers)
        r = client.get("/api/employees", headers=tenant_headers)
        assert r.status_code == 200
        names = [e["name"] for e in r.json()]
        assert name in names

    def test_requires_authentication(self, client, tenant):
        r = client.get("/api/employees", headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestUpdateEmployee:
    def test_update_fields(self, client, tenant_headers):
        emp = client.post("/api/employees", json={"name": f"Dave {_uid()}"}, headers=tenant_headers).json()
        uid = _uid()
        r = client.put(f"/api/employees/{emp['id']}", json={
            "name": f"Dave Updated {uid}",
            "email": f"dave{uid}@updated.com",
            "department": "Operations",
        }, headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["department"] == "Operations"
        assert "updated" in data["name"]

    def test_update_not_found(self, client, tenant_headers):
        r = client.put("/api/employees/999999", json={"name": "X"}, headers=tenant_headers)
        assert r.status_code == 404


class TestDeleteEmployee:
    def test_delete(self, client, tenant_headers):
        emp = client.post("/api/employees", json={"name": f"Eve {_uid()}"}, headers=tenant_headers).json()
        r = client.delete(f"/api/employees/{emp['id']}", headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete_not_found(self, client, tenant_headers):
        r = client.delete("/api/employees/999999", headers=tenant_headers)
        assert r.status_code == 404

    def test_delete_blocked_when_assets_assigned(self, client, tenant_headers):
        emp = client.post("/api/employees", json={"name": f"Frank {_uid()}"}, headers=tenant_headers).json()
        client.post("/api/assets", json={
            "asset_tag": _tag(), "name": "Assigned Laptop", "status": "deployed",
            "assigned_to_id": emp["id"],
        }, headers=tenant_headers)
        r = client.delete(f"/api/employees/{emp['id']}", headers=tenant_headers)
        assert r.status_code == 400
