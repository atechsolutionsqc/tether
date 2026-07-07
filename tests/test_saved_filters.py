"""
test_saved_filters.py — Saved search / filter views.

Covers:
  - Create and retrieve saved filters
  - Filters are user-scoped (other users cannot see them)
  - Delete own filter
  - Cannot delete another user's filter
  - Auth required
"""
import time


def _uid():
    return int(time.time() * 1000) % 999999


class TestSavedFilters:
    def test_create_and_list(self, client, tenant_headers):
        uid = _uid()
        r = client.post("/api/saved-filters", json={
            "name": f"Deployed Laptops {uid}",
            "filters": {"status": "deployed", "q": "laptop"},
        }, headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["name"] == f"Deployed Laptops {uid}"
        assert d["filters"]["status"] == "deployed"

        r2 = client.get("/api/saved-filters", headers=tenant_headers)
        assert r2.status_code == 200
        names = [v["name"] for v in r2.json()]
        assert f"Deployed Laptops {uid}" in names

    def test_delete_own_filter(self, client, tenant_headers):
        uid = _uid()
        created = client.post("/api/saved-filters", json={
            "name": f"ToDelete {uid}", "filters": {},
        }, headers=tenant_headers).json()
        r = client.delete(f"/api/saved-filters/{created['id']}", headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["ok"] is True
        r2 = client.get("/api/saved-filters", headers=tenant_headers)
        assert not any(v["id"] == created["id"] for v in r2.json())

    def test_user_scoped_cannot_see_others(self, client, auth, roles, tenant):
        uid = _uid()
        r = client.post("/api/users", json={
            "name": f"SF User {uid}", "email": f"sf{uid}@example.com",
            "password": "Password123!", "role_id": roles["client_admin"]["id"],
            "tenant_id": tenant["id"], "is_msp_staff": False,
        }, headers=auth)
        assert r.status_code == 200
        lr = client.post("/api/auth/login",
                         data={"username": f"sf{uid}@example.com", "password": "Password123!"},
                         headers={"host": f"{tenant['slug']}.localhost"})
        other_auth = {"Authorization": f"Bearer {lr.json()['access_token']}",
                      "host": f"{tenant['slug']}.localhost"}

        # other user creates a filter
        client.post("/api/saved-filters", json={"name": f"OtherView {uid}", "filters": {}}, headers=other_auth)

        # original user's list should not contain it
        r2 = client.get("/api/saved-filters", headers={"Authorization": auth["Authorization"],
                                                        "host": f"{tenant['slug']}.localhost"})
        names = [v["name"] for v in r2.json()]
        assert f"OtherView {uid}" not in names

    def test_cannot_delete_other_users_filter(self, client, auth, roles, tenant):
        uid = _uid()
        r = client.post("/api/users", json={
            "name": f"SF2 {uid}", "email": f"sf2{uid}@example.com",
            "password": "Password123!", "role_id": roles["client_admin"]["id"],
            "tenant_id": tenant["id"], "is_msp_staff": False,
        }, headers=auth)
        lr = client.post("/api/auth/login",
                         data={"username": f"sf2{uid}@example.com", "password": "Password123!"},
                         headers={"host": f"{tenant['slug']}.localhost"})
        other_auth = {"Authorization": f"Bearer {lr.json()['access_token']}",
                      "host": f"{tenant['slug']}.localhost"}
        created = client.post("/api/saved-filters", json={"name": f"Mine {uid}", "filters": {}}, headers=other_auth).json()

        # original MSP user tries to delete other's filter
        r2 = client.delete(f"/api/saved-filters/{created['id']}", headers=auth)
        assert r2.status_code == 404

    def test_requires_auth(self, client, tenant):
        r = client.get("/api/saved-filters", headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401
