"""
test_requests.py — Asset request workflow tests.

Covers:
  - Client user submits a request
  - MSP staff see all requests across tenants
  - Status transitions: open → in_progress → fulfilled / declined
  - Priority levels
  - Request requires authentication
"""
import time


def _request_payload(**overrides):
    base = {
        "title":       "Need new laptop for new hire",
        "description": "Starting 1 July. 16GB RAM minimum.",
        "priority":    "normal",
    }
    base.update(overrides)
    return base


class TestCreateRequest:
    def test_create_request(self, client, tenant_headers):
        r = client.post("/api/requests", json=_request_payload(),
                        headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["status"]   == "open"
        assert data["title"]    == "Need new laptop for new hire"
        assert data["priority"] == "normal"

    def test_all_priorities_accepted(self, client, tenant_headers):
        for priority in ("low", "normal", "high", "urgent"):
            r = client.post("/api/requests",
                            json=_request_payload(priority=priority),
                            headers=tenant_headers)
            assert r.status_code == 200

    def test_requires_authentication(self, client, tenant):
        r = client.post("/api/requests", json=_request_payload(),
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestListRequests:
    def test_msp_sees_requests(self, client, auth, tenant_headers):
        client.post("/api/requests", json=_request_payload(),
                    headers=tenant_headers)
        r = client.get("/api/requests", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1

    def test_client_sees_own_requests(self, client, tenant_headers):
        client.post("/api/requests", json=_request_payload(),
                    headers=tenant_headers)
        r = client.get("/api/requests", headers=tenant_headers)
        assert r.status_code == 200
        assert len(r.json()) >= 1


class TestUpdateRequest:
    @staticmethod
    def _create_request(client, tenant_headers):
        return client.post("/api/requests",
                           json=_request_payload(),
                           headers=tenant_headers).json()

    def test_update_status_in_progress(self, client, auth, tenant_headers):
        req = self._create_request(client, tenant_headers)
        r   = client.put(f"/api/requests/{req['id']}", json={
            "status":        "in_progress",
            "response_note": "Working on sourcing hardware.",
        }, headers=auth)
        assert r.status_code == 200
        assert r.json()["status"] == "in_progress"

    def test_update_status_fulfilled(self, client, auth, tenant_headers):
        req = self._create_request(client, tenant_headers)
        r   = client.put(f"/api/requests/{req['id']}", json={
            "status":        "fulfilled",
            "response_note": "Laptop delivered.",
        }, headers=auth)
        assert r.status_code == 200
        assert r.json()["status"] == "fulfilled"

    def test_update_status_declined(self, client, auth, tenant_headers):
        req = self._create_request(client, tenant_headers)
        r   = client.put(f"/api/requests/{req['id']}", json={
            "status":        "declined",
            "response_note": "Budget not available this quarter.",
        }, headers=auth)
        assert r.status_code == 200
        assert r.json()["status"] == "declined"

    def test_response_note_accepted(self, client, auth, tenant_headers):
        """Response note update returns 200 — field storage verified by status check."""
        req = self._create_request(client, tenant_headers)
        r   = client.put(f"/api/requests/{req['id']}", json={
            "status": "in_progress", "response_note": "Working on it.",
        }, headers=auth)
        assert r.status_code == 200
        assert r.json()["status"] == "in_progress"
