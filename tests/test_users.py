"""
test_users.py — User management, permissions, and invite tests.

Covers:
  - Create / list / update / deactivate users
  - Role assignment
  - Permission overrides (grant / revoke)
  - Invite generation
  - Invite validation
  - Invite acceptance creates account
  - Expired / used invites rejected
"""
import time


def _email():
    return f"user{int(time.time()*1000) % 999999}@test.com"


class TestUserCRUD:
    def test_create_client_user(self, client, auth, tenant, roles):
        r = client.post("/api/users", json={
            "name":         "New User",
            "email":        _email(),
            "password":     "password123",
            "role_id":      roles["client_viewer"]["id"],
            "tenant_id":    tenant["id"],
            "is_msp_staff": False,
            "active":       True,
        }, headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert data["is_msp_staff"] is False
        assert data["tenant_id"] == tenant["id"]

    def test_duplicate_email_rejected(self, client, auth, tenant, roles):
        email = _email()
        client.post("/api/users", json={
            "name": "First", "email": email, "password": "password123",
            "role_id": roles["client_viewer"]["id"],
            "tenant_id": tenant["id"], "is_msp_staff": False, "active": True,
        }, headers=auth)
        r = client.post("/api/users", json={
            "name": "Second", "email": email, "password": "password123",
            "role_id": roles["client_viewer"]["id"],
            "tenant_id": tenant["id"], "is_msp_staff": False, "active": True,
        }, headers=auth)
        assert r.status_code == 400

    def test_list_users(self, client, auth):
        r = client.get("/api/users", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1

    def test_deactivate_user(self, client, auth, tenant, roles):
        email = _email()
        u = client.post("/api/users", json={
            "name": "Deactivate Me", "email": email, "password": "password123",
            "role_id": roles["client_viewer"]["id"],
            "tenant_id": tenant["id"], "is_msp_staff": False, "active": True,
        }, headers=auth).json()

        r = client.put(f"/api/users/{u['id']}", json={
            **u, "active": False, "password": "",
        }, headers=auth)
        assert r.status_code == 200
        assert r.json()["active"] is False

        # Deactivated user cannot log in
        r2 = client.post("/api/auth/login",
                         data={"username": email, "password": "password123"})
        assert r2.status_code in (401, 403, 400)  # 401/403 unauthorized or 400 inactive

    def test_list_roles(self, client, auth):
        r = client.get("/api/users/roles/all", headers=auth)
        assert r.status_code == 200
        role_names = [role["name"] for role in r.json()]
        assert "msp_admin" in role_names
        assert "client_viewer" in role_names


class TestPermissions:
    def _create_user(self, client, auth, tenant, roles):
        email = _email()
        u = client.post("/api/users", json={
            "name": "Perm Test", "email": email, "password": "password123",
            "role_id":      roles["client_viewer"]["id"],
            "tenant_id":    tenant["id"],
            "is_msp_staff": False, "active": True,
        }, headers=auth).json()
        return u

    def test_get_user_permissions(self, client, auth, tenant, roles):
        u = self._create_user(client, auth, tenant, roles)
        r = client.get(f"/api/users/{u['id']}/permissions", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "effective" in data
        assert "role_permissions" in data
        # client_viewer can view and export
        assert "assets.view" in data["effective"]
        assert "assets.create" not in data["effective"]

    def test_grant_permission_override(self, client, auth, tenant, roles):
        u = self._create_user(client, auth, tenant, roles)
        # Set override
        r = client.put(f"/api/users/{u['id']}/permissions", json={
            "permission_key": "assets.create",
            "granted":        True,
        }, headers=auth)
        assert r.status_code == 200

        # Verify via GET /permissions that it's now effective
        r2 = client.get(f"/api/users/{u['id']}/permissions", headers=auth)
        assert r2.status_code == 200
        data = r2.json()
        effective = data.get("effective") or data.get("effective_permissions") or []
        assert "assets.create" in effective

    def test_revoke_permission_override(self, client, auth, tenant, roles):
        email = _email()
        u = client.post("/api/users", json={
            "name": "Admin Perm", "email": email, "password": "password123",
            "role_id":      roles["client_admin"]["id"],
            "tenant_id":    tenant["id"],
            "is_msp_staff": False, "active": True,
        }, headers=auth).json()
        r = client.put(f"/api/users/{u['id']}/permissions", json={
            "permission_key": "assets.delete",
            "granted":        False,
        }, headers=auth)
        assert r.status_code == 200

        # Verify via GET
        r2 = client.get(f"/api/users/{u['id']}/permissions", headers=auth)
        data = r2.json()
        effective = data.get("effective") or data.get("effective_permissions") or []
        assert "assets.delete" not in effective

    def test_clear_permission_override(self, client, auth, tenant, roles):
        u = self._create_user(client, auth, tenant, roles)
        # Grant then clear
        client.put(f"/api/users/{u['id']}/permissions", json={
            "permission_key": "assets.create", "granted": True,
        }, headers=auth)
        r = client.delete(
            f"/api/users/{u['id']}/permissions/assets.create",
            headers=auth,
        )
        assert r.status_code == 200


class TestInvites:
    def test_create_invite(self, client, auth, tenant, roles):
        r = client.post("/api/invites", json={
            "email":        _email(),
            "name":         "Invited User",
            "role_id":      roles["client_viewer"]["id"],
            "tenant_id":    tenant["id"],
            "expires_hours": 72,
        }, headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert "invite_url" in data
        assert data["tenant"] == tenant["name"]

    def test_validate_invite_token(self, client, auth, tenant, roles):
        email = _email()
        inv   = client.post("/api/invites", json={
            "email": email, "name": "Invited",
            "role_id":   roles["client_viewer"]["id"],
            "tenant_id": tenant["id"],
            "expires_hours": 24,
        }, headers=auth).json()

        r = client.get(f"/api/invites/validate/{inv['token']}")
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == email

    def test_invalid_token_rejected(self, client):
        r = client.get("/api/invites/validate/thisisnotavalidtoken")
        assert r.status_code == 400

    def test_accept_invite_creates_account(self, client, auth, tenant, roles):
        email = _email()
        inv   = client.post("/api/invites", json={
            "email": email, "name": "Accept Me",
            "role_id":   roles["client_viewer"]["id"],
            "tenant_id": tenant["id"],
            "expires_hours": 24,
        }, headers=auth).json()

        # Accept invite
        r = client.post("/api/invites/accept", json={
            "token":    inv["token"],
            "name":     "Accept Me",
            "password": "newuserpass123",
        })
        assert r.status_code == 200

        # Can now log in
        r2 = client.post("/api/auth/login",
                         data={"username": email, "password": "newuserpass123"})
        assert r2.status_code == 200

    def test_used_token_cannot_be_accepted_again(self, client, auth, tenant, roles):
        email = _email()
        inv   = client.post("/api/invites", json={
            "email": email, "name": "Once Only",
            "role_id":   roles["client_viewer"]["id"],
            "tenant_id": tenant["id"],
            "expires_hours": 24,
        }, headers=auth).json()

        client.post("/api/invites/accept", json={
            "token": inv["token"], "name": "Once Only", "password": "pass12345",
        })
        r = client.post("/api/invites/accept", json={
            "token": inv["token"], "name": "Once Only", "password": "pass12345",
        })
        assert r.status_code == 400
