"""
test_licences.py — Software licence management tests.

Covers:
  - Create returns correct shape including seats_used=0
  - Assign seat increments seats_used
  - Unassign seat decrements seats_used
  - Cannot assign beyond total_seats (400)
  - Unlimited seats (total_seats=null) never blocks assignment
  - Delete cascades to assignments
  - Expiring endpoint respects days param
  - Cross-tenant isolation: cannot assign employee from another tenant
  - Requires authentication
"""
import time
from datetime import date, timedelta


def _lic_payload(**kwargs):
    base = {
        "name": f"TestLicence-{int(time.time()*1000)%999999}",
        "vendor": "Acme Corp",
        "licence_type": "per-seat",
        "total_seats": 5,
    }
    base.update(kwargs)
    return base


class TestCreateLicence:
    def test_create_returns_correct_shape(self, client, tenant_headers):
        r = client.post("/api/licences", json=_lic_payload(), headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["name"].startswith("TestLicence")
        assert d["vendor"] == "Acme Corp"
        assert d["seats_used"] == 0
        assert d["total_seats"] == 5
        assert d["seats_available"] == 5
        assert "id" in d

    def test_create_unlimited_seats(self, client, tenant_headers):
        r = client.post("/api/licences",
                        json=_lic_payload(total_seats=None),
                        headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["total_seats"] is None
        assert d["seats_available"] is None

    def test_requires_authentication(self, client, tenant):
        r = client.post("/api/licences",
                        json=_lic_payload(),
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401

    def test_create_with_all_fields(self, client, tenant_headers):
        today = date.today().isoformat()
        future = (date.today() + timedelta(days=365)).isoformat()
        r = client.post("/api/licences", json={
            "name": "Full Licence",
            "vendor": "Vendor X",
            "licence_type": "site",
            "total_seats": 100,
            "purchase_date": today,
            "expiry_date": future,
            "purchase_cost": 999.99,
            "renewal_cost": 799.00,
            "licence_key": "XXXX-YYYY-ZZZZ",
            "notes": "Site licence for main office",
        }, headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["purchase_cost"] == 999.99
        assert d["expiry_date"] == future
        assert d["licence_key"] == "XXXX-YYYY-ZZZZ"


class TestAssignUnassign:
    def _create_licence(self, client, tenant_headers, seats=3):
        r = client.post("/api/licences",
                        json=_lic_payload(total_seats=seats),
                        headers=tenant_headers)
        assert r.status_code == 200
        return r.json()

    def test_assign_increments_seats_used(self, client, tenant_headers, fresh_employee):
        lic = self._create_licence(client, tenant_headers)
        assert lic["seats_used"] == 0

        r = client.post(f"/api/licences/{lic['id']}/assign",
                        json={"employee_id": fresh_employee["id"], "notes": ""},
                        headers=tenant_headers)
        assert r.status_code == 200

        r2 = client.get(f"/api/licences/{lic['id']}", headers=tenant_headers)
        assert r2.json()["seats_used"] == 1

    def test_unassign_decrements_seats_used(self, client, tenant_headers, fresh_employee):
        lic = self._create_licence(client, tenant_headers)

        ra = client.post(f"/api/licences/{lic['id']}/assign",
                         json={"employee_id": fresh_employee["id"]},
                         headers=tenant_headers)
        assert ra.status_code == 200
        assign_id = ra.json()["id"]

        client.delete(f"/api/licences/{lic['id']}/assign/{assign_id}",
                      headers=tenant_headers)

        r2 = client.get(f"/api/licences/{lic['id']}", headers=tenant_headers)
        assert r2.json()["seats_used"] == 0

    def test_cannot_assign_beyond_total_seats(self, client, tenant_headers, fresh_employee):
        lic = self._create_licence(client, tenant_headers, seats=1)

        r1 = client.post(f"/api/licences/{lic['id']}/assign",
                         json={"employee_id": fresh_employee["id"]},
                         headers=tenant_headers)
        assert r1.status_code == 200

        r2 = client.post(f"/api/licences/{lic['id']}/assign",
                         json={"employee_id": fresh_employee["id"]},
                         headers=tenant_headers)
        assert r2.status_code == 400
        assert "seats" in r2.json()["detail"].lower()

    def test_unlimited_seats_never_blocks(self, client, tenant_headers, fresh_employee):
        lic_r = client.post("/api/licences",
                            json=_lic_payload(total_seats=None),
                            headers=tenant_headers)
        lic = lic_r.json()

        for _ in range(5):
            r = client.post(f"/api/licences/{lic['id']}/assign",
                            json={"employee_id": fresh_employee["id"]},
                            headers=tenant_headers)
            assert r.status_code == 200

        r2 = client.get(f"/api/licences/{lic['id']}", headers=tenant_headers)
        assert r2.json()["seats_used"] == 5

    def test_assign_with_asset(self, client, tenant_headers, fresh_asset):
        lic = self._create_licence(client, tenant_headers)
        r = client.post(f"/api/licences/{lic['id']}/assign",
                        json={"asset_id": fresh_asset["id"], "notes": "device licence"},
                        headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["asset_id"] == fresh_asset["id"]
        assert d["asset_tag"] == fresh_asset["asset_tag"]

    def test_assignments_appear_in_detail_view(self, client, tenant_headers, fresh_employee):
        lic = self._create_licence(client, tenant_headers)
        client.post(f"/api/licences/{lic['id']}/assign",
                    json={"employee_id": fresh_employee["id"]},
                    headers=tenant_headers)

        r = client.get(f"/api/licences/{lic['id']}", headers=tenant_headers)
        data = r.json()
        assert "assignments" in data
        assert len(data["assignments"]) == 1
        assert data["assignments"][0]["employee_id"] == fresh_employee["id"]


class TestDeleteLicence:
    def test_delete_cascades_to_assignments(self, client, tenant_headers, fresh_employee):
        lic_r = client.post("/api/licences",
                            json=_lic_payload(total_seats=10),
                            headers=tenant_headers)
        lic = lic_r.json()

        client.post(f"/api/licences/{lic['id']}/assign",
                    json={"employee_id": fresh_employee["id"]},
                    headers=tenant_headers)

        r_del = client.delete(f"/api/licences/{lic['id']}", headers=tenant_headers)
        assert r_del.status_code == 200

        r_get = client.get(f"/api/licences/{lic['id']}", headers=tenant_headers)
        assert r_get.status_code == 404

    def test_delete_nonexistent_returns_404(self, client, tenant_headers):
        r = client.delete("/api/licences/999999", headers=tenant_headers)
        assert r.status_code == 404


class TestExpiringEndpoint:
    def test_expiring_respects_days_param(self, client, tenant_headers):
        soon = (date.today() + timedelta(days=30)).isoformat()
        far  = (date.today() + timedelta(days=200)).isoformat()

        soon_r = client.post("/api/licences",
                             json=_lic_payload(expiry_date=soon),
                             headers=tenant_headers)
        far_r  = client.post("/api/licences",
                             json=_lic_payload(expiry_date=far),
                             headers=tenant_headers)
        soon_id = soon_r.json()["id"]
        far_id  = far_r.json()["id"]

        # /expiring?days=60 should include soon but not far
        r = client.get("/api/licences/expiring?days=60", headers=tenant_headers)
        assert r.status_code == 200
        ids = [l["id"] for l in r.json()]
        assert soon_id in ids
        assert far_id not in ids

    def test_expiring_default_90_days(self, client, tenant_headers):
        within = (date.today() + timedelta(days=89)).isoformat()
        outside = (date.today() + timedelta(days=120)).isoformat()

        in_r  = client.post("/api/licences", json=_lic_payload(expiry_date=within),
                            headers=tenant_headers)
        out_r = client.post("/api/licences", json=_lic_payload(expiry_date=outside),
                            headers=tenant_headers)
        in_id  = in_r.json()["id"]
        out_id = out_r.json()["id"]

        r = client.get("/api/licences/expiring", headers=tenant_headers)
        ids = [l["id"] for l in r.json()]
        assert in_id in ids
        assert out_id not in ids

    def test_already_expired_not_returned(self, client, tenant_headers):
        past = (date.today() - timedelta(days=1)).isoformat()
        r = client.post("/api/licences", json=_lic_payload(expiry_date=past),
                        headers=tenant_headers)
        expired_id = r.json()["id"]

        r2 = client.get("/api/licences/expiring?days=365", headers=tenant_headers)
        ids = [l["id"] for l in r2.json()]
        assert expired_id not in ids


class TestCrossTenantIsolation:
    def _make_second_tenant_and_headers(self, client, auth):
        slug = f"iso-{int(time.time()*1000)%999999}"
        r = client.post("/api/tenants", json={"name": "Isolation Corp", "slug": slug},
                        headers=auth)
        assert r.status_code == 200
        t2 = r.json()

        # Get a token for tenant2 by creating a user there
        role_r = client.get("/api/users/roles/all", headers=auth)
        roles = {role["name"]: role for role in role_r.json()}
        admin_role = roles.get("client_admin", roles[list(roles.keys())[0]])

        uid = int(time.time()*1000) % 999999
        email = f"iso{uid}@iso.test"
        user_r = client.post("/api/users", json={
            "name":     "ISO User",
            "email":    email,
            "password": "isopass123",
            "role_id":  admin_role["id"],
            "tenant_id": t2["id"],
        }, headers=auth)
        assert user_r.status_code == 200

        login = client.post("/api/auth/login",
                            data={"username": email, "password": "isopass123"},
                            headers={"host": f"{slug}.localhost"})
        assert login.status_code == 200
        token = login.json()["access_token"]
        t2_headers = {"Authorization": f"Bearer {token}", "host": f"{slug}.localhost"}
        return t2, t2_headers

    def test_cannot_see_other_tenant_licences(self, client, auth, tenant_headers, tenant):
        t2, t2_headers = self._make_second_tenant_and_headers(client, auth)

        r = client.post("/api/licences", json=_lic_payload(), headers=tenant_headers)
        lic = r.json()

        r2 = client.get(f"/api/licences/{lic['id']}", headers=t2_headers)
        assert r2.status_code == 404

    def test_cannot_assign_employee_from_another_tenant(
        self, client, auth, tenant_headers, fresh_employee
    ):
        t2, t2_headers = self._make_second_tenant_and_headers(client, auth)

        # Create a licence in tenant2
        lic_r = client.post("/api/licences", json=_lic_payload(), headers=t2_headers)
        lic = lic_r.json()

        # Try to assign tenant1's employee to tenant2's licence via tenant2's scoped call
        r = client.post(f"/api/licences/{lic['id']}/assign",
                        json={"employee_id": fresh_employee["id"]},
                        headers=t2_headers)
        assert r.status_code == 400

    def test_list_only_returns_own_tenant_licences(
        self, client, auth, tenant_headers
    ):
        t2, t2_headers = self._make_second_tenant_and_headers(client, auth)

        r1 = client.post("/api/licences", json=_lic_payload(name="T1-Licence"),
                         headers=tenant_headers)
        r2 = client.post("/api/licences", json=_lic_payload(name="T2-Licence"),
                         headers=t2_headers)
        t1_id = r1.json()["id"]
        t2_id = r2.json()["id"]

        t1_list = [l["id"] for l in client.get("/api/licences", headers=tenant_headers).json()]
        t2_list = [l["id"] for l in client.get("/api/licences", headers=t2_headers).json()]

        assert t1_id in t1_list
        assert t2_id not in t1_list
        assert t2_id in t2_list
        assert t1_id not in t2_list


class TestAuthentication:
    def test_list_requires_auth(self, client, tenant):
        r = client.get("/api/licences",
                       headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401

    def test_create_requires_auth(self, client, tenant):
        r = client.post("/api/licences", json=_lic_payload(),
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401

    def test_delete_requires_auth(self, client, tenant):
        r = client.delete("/api/licences/1",
                          headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401
