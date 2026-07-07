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
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_created_employee_appears(self, client, tenant_headers):
        uid = _uid()
        name = f"Carol {uid}"
        client.post("/api/employees", json={"name": name}, headers=tenant_headers)
        r = client.get("/api/employees", headers=tenant_headers)
        assert r.status_code == 200
        names = [e["name"] for e in r.json()["items"]]
        assert name in names

    def test_requires_authentication(self, client, tenant):
        r = client.get("/api/employees", headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestUpdateEmployee:
    def test_update_fields(self, client, tenant_headers):
        emp = client.post("/api/employees", json={"name": f"Dave {_uid()}"}, headers=tenant_headers).json()
        uid = _uid()
        new_name = f"Dave Updated {uid}"
        r = client.put(f"/api/employees/{emp['id']}", json={
            "name": new_name,
            "email": f"dave{uid}@updated.com",
            "department": "Operations",
        }, headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == new_name
        assert data["department"] == "Operations"

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


class TestDepartments:
    def test_departments_empty_when_no_employees(self, client, tenant_headers):
        r = client.get("/api/employees/departments", headers=tenant_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_departments_returns_distinct_values(self, client, tenant_headers):
        uid = _uid()
        client.post("/api/employees", json={"name": f"D1 {uid}", "department": f"Eng{uid}"}, headers=tenant_headers)
        client.post("/api/employees", json={"name": f"D2 {uid}", "department": f"Eng{uid}"}, headers=tenant_headers)
        client.post("/api/employees", json={"name": f"D3 {uid}", "department": f"Ops{uid}"}, headers=tenant_headers)
        r = client.get("/api/employees/departments", headers=tenant_headers)
        depts = r.json()
        assert depts.count(f"Eng{uid}") == 1
        assert f"Ops{uid}" in depts

    def test_departments_excludes_empty(self, client, tenant_headers):
        client.post("/api/employees", json={"name": f"NoDept {_uid()}"}, headers=tenant_headers)
        r = client.get("/api/employees/departments", headers=tenant_headers)
        assert "" not in r.json()

    def test_department_filter_on_assets(self, client, tenant_headers):
        uid = _uid()
        dept = f"FilterDept{uid}"
        emp = client.post("/api/employees", json={"name": f"FEmp {uid}", "department": dept}, headers=tenant_headers).json()
        asset = client.post("/api/assets", json={"asset_tag": _tag(), "name": "DeptAsset", "status": "deployed",
                                                  "assigned_to_id": emp["id"]}, headers=tenant_headers).json()
        r = client.get(f"/api/assets?department={dept}", headers=tenant_headers)
        assert r.status_code == 200
        tags = [a["asset_tag"] for a in r.json()["items"]]
        assert asset["asset_tag"] in tags

    def test_departments_requires_auth(self, client, tenant):
        r = client.get("/api/employees/departments", headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestBulkReassign:
    def test_reassign_to_another_employee(self, client, tenant_headers):
        src = client.post("/api/employees", json={"name": f"Src {_uid()}"}, headers=tenant_headers).json()
        dst = client.post("/api/employees", json={"name": f"Dst {_uid()}"}, headers=tenant_headers).json()
        asset = client.post("/api/assets", json={"asset_tag": _tag(), "name": "ReassignMe", "status": "deployed",
                                                  "assigned_to_id": src["id"]}, headers=tenant_headers).json()
        r = client.post(f"/api/employees/{src['id']}/reassign",
                        json={"to_employee_id": dst["id"]}, headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["moved"] == 1
        assert d["to_employee_id"] == dst["id"]
        # Verify asset now belongs to dst
        a = client.get(f"/api/assets/{asset['id']}", headers=tenant_headers).json()
        assert a["assigned_to_id"] == dst["id"]

    def test_reassign_to_unassigned(self, client, tenant_headers):
        src = client.post("/api/employees", json={"name": f"Src2 {_uid()}"}, headers=tenant_headers).json()
        asset = client.post("/api/assets", json={"asset_tag": _tag(), "name": "FreeMe", "status": "deployed",
                                                  "assigned_to_id": src["id"]}, headers=tenant_headers).json()
        r = client.post(f"/api/employees/{src['id']}/reassign",
                        json={"to_employee_id": None}, headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["to_employee_id"] is None
        a = client.get(f"/api/assets/{asset['id']}", headers=tenant_headers).json()
        assert a["assigned_to_id"] is None
        assert a["status"] == "available"

    def test_reassign_allows_delete(self, client, tenant_headers):
        src = client.post("/api/employees", json={"name": f"DelSrc {_uid()}"}, headers=tenant_headers).json()
        client.post("/api/assets", json={"asset_tag": _tag(), "name": "BlockingAsset", "status": "deployed",
                                         "assigned_to_id": src["id"]}, headers=tenant_headers)
        # Delete should fail first
        assert client.delete(f"/api/employees/{src['id']}", headers=tenant_headers).status_code == 400
        # Reassign, then delete should succeed
        client.post(f"/api/employees/{src['id']}/reassign", json={"to_employee_id": None}, headers=tenant_headers)
        assert client.delete(f"/api/employees/{src['id']}", headers=tenant_headers).status_code == 200

    def test_reassign_requires_auth(self, client, fresh_employee, tenant):
        r = client.post(f"/api/employees/{fresh_employee['id']}/reassign",
                        json={"to_employee_id": None},
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401

    def test_reassign_cross_tenant_rejected(self, client, auth, roles, tenant, fresh_employee):
        r = client.post("/api/tenants", json={"name": "ReassignB", "slug": "reassignb", "currency": "USD"}, headers=auth)
        tid_b = r.json()["id"]
        r = client.post("/api/users", json={
            "name": "ReassignB User", "email": "reassignb@fixture.com",
            "password": "Password123!", "role_id": roles["client_admin"]["id"],
            "tenant_id": tid_b, "is_msp_staff": False,
        }, headers=auth)
        lr = client.post("/api/auth/login", data={"username": "reassignb@fixture.com", "password": "Password123!"})
        b_auth = {"Authorization": f"Bearer {lr.json()['access_token']}", "host": "reassignb.localhost"}
        r = client.post(f"/api/employees/{fresh_employee['id']}/reassign",
                        json={"to_employee_id": None}, headers=b_auth)
        assert r.status_code == 404


class TestEmployeeHistory:
    def test_history_empty_for_new_employee(self, client, tenant_headers):
        emp = client.post("/api/employees", json={"name": f"HistNew {_uid()}"}, headers=tenant_headers).json()
        r = client.get(f"/api/employees/{emp['id']}/history", headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert "employee" in d
        assert "history" in d
        assert d["history"] == []

    def test_history_records_checkout(self, client, tenant_headers):
        emp   = client.post("/api/employees", json={"name": f"HistUser {_uid()}"}, headers=tenant_headers).json()
        asset = client.post("/api/assets", json={"asset_tag": _tag(), "name": "Hist Asset", "status": "available"}, headers=tenant_headers).json()
        # Check out to employee
        client.post(f"/api/assets/{asset['id']}/checkout", json={"employee_id": emp["id"]}, headers=tenant_headers)
        r = client.get(f"/api/employees/{emp['id']}/history", headers=tenant_headers)
        assert r.status_code == 200
        hist = r.json()["history"]
        assert len(hist) >= 1
        assert any(h["action"] == "checkout" and h["asset_tag"] == asset["asset_tag"] for h in hist)

    def test_history_includes_currently_assigned_flag(self, client, tenant_headers):
        emp   = client.post("/api/employees", json={"name": f"HistCurr {_uid()}"}, headers=tenant_headers).json()
        asset = client.post("/api/assets", json={"asset_tag": _tag(), "name": "Curr Asset", "status": "available"}, headers=tenant_headers).json()
        client.post(f"/api/assets/{asset['id']}/checkout", json={"employee_id": emp["id"]}, headers=tenant_headers)
        r = client.get(f"/api/employees/{emp['id']}/history", headers=tenant_headers)
        hist = r.json()["history"]
        assert any(h["currently_assigned"] is True for h in hist)

    def test_history_requires_auth(self, client, fresh_employee, tenant):
        r = client.get(f"/api/employees/{fresh_employee['id']}/history")
        assert r.status_code == 401

    def test_history_cross_tenant_isolation(self, client, auth, roles, tenant, fresh_employee):
        """A client user from another tenant cannot see this employee's history."""
        r = client.post("/api/tenants", json={"name": "Hist Tenant B", "slug": "histb", "currency": "USD"}, headers=auth)
        assert r.status_code == 200
        tid_b = r.json()["id"]
        r = client.post("/api/users", json={
            "name": "Hist B User", "email": "histb@fixture.com",
            "password": "Password123!", "role_id": roles["client_admin"]["id"],
            "tenant_id": tid_b, "is_msp_staff": False,
        }, headers=auth)
        assert r.status_code == 200
        lr = client.post("/api/auth/login", data={"username": "histb@fixture.com", "password": "Password123!"})
        b_auth = {"Authorization": f"Bearer {lr.json()['access_token']}", "host": "histb.localhost"}
        r = client.get(f"/api/employees/{fresh_employee['id']}/history", headers=b_auth)
        assert r.status_code == 404
