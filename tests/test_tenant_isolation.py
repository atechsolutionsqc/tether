"""
test_tenant_isolation.py — Cross-tenant data isolation tests.

Verifies that tenant A cannot read, modify, or delete resources belonging to tenant B.
Covers the three security fixes:
  1. employees.py  — update/delete cross-tenant blocked
  2. saved_filters.py — delete cross-tenant blocked
  3. custom_fields.py — values scoped to requesting tenant
"""
import time
import pytest


def _uid():
    return int(time.time() * 1000) % 99999999


# ── Fixtures: second isolated tenant ─────────────────────────────────────────

@pytest.fixture(scope="module")
def tenant_b(client, auth):
    """A second tenant for cross-tenant tests."""
    slug = f"isolation-b-{_uid()}"
    r = client.post("/api/tenants", json={
        "name": f"Isolation Corp B {_uid()}",
        "slug": slug,
        "currency": "USD",
    }, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def tenant_b_headers(auth, tenant_b):
    return {**auth, "host": f"{tenant_b['slug']}.localhost"}


@pytest.fixture(scope="module")
def tenant_a(client, auth):
    """A first tenant for cross-tenant tests (separate from conftest 'tenant')."""
    slug = f"isolation-a-{_uid()}"
    r = client.post("/api/tenants", json={
        "name": f"Isolation Corp A {_uid()}",
        "slug": slug,
        "currency": "CAD",
    }, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def tenant_a_headers(auth, tenant_a):
    return {**auth, "host": f"{tenant_a['slug']}.localhost"}


# ── Employee isolation ────────────────────────────────────────────────────────

class TestEmployeeTenantIsolation:
    """Tenant A cannot update or delete employees belonging to Tenant B."""

    @pytest.fixture(scope="class")
    def emp_in_b(self, client, tenant_b_headers):
        r = client.post("/api/employees", json={
            "name": f"Employee B {_uid()}",
            "email": f"empb{_uid()}@b.com",
        }, headers=tenant_b_headers)
        assert r.status_code == 200, r.text
        return r.json()

    def test_update_cross_tenant_blocked(self, client, tenant_a_headers, emp_in_b):
        """Tenant A cannot update an employee that belongs to Tenant B."""
        r = client.put(f"/api/employees/{emp_in_b['id']}",
                       json={"name": "Hacked", "email": "hacked@evil.com"},
                       headers=tenant_a_headers)
        assert r.status_code == 404

    def test_delete_cross_tenant_blocked(self, client, tenant_a_headers, emp_in_b):
        """Tenant A cannot delete an employee that belongs to Tenant B."""
        r = client.delete(f"/api/employees/{emp_in_b['id']}",
                          headers=tenant_a_headers)
        assert r.status_code == 404

    def test_employee_still_exists_after_failed_attacks(self, client, tenant_b_headers, emp_in_b):
        """Employee B is intact after the failed cross-tenant attempts."""
        r = client.get("/api/employees", headers=tenant_b_headers)
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()["items"]]
        assert emp_in_b["id"] in ids

    def test_list_employees_does_not_cross_leak(self, client, tenant_a_headers, emp_in_b):
        """Tenant A's employee list does not contain Tenant B's employee."""
        r = client.get("/api/employees", headers=tenant_a_headers)
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()["items"]]
        assert emp_in_b["id"] not in ids


# ── Saved filter isolation ────────────────────────────────────────────────────

class TestSavedFilterTenantIsolation:
    """Tenant A cannot delete saved filters belonging to Tenant B."""

    @pytest.fixture(scope="class")
    def filter_in_b(self, client, tenant_b_headers):
        r = client.post("/api/saved-filters", json={
            "name": f"Filter B {_uid()}",
            "filters": {"status": "available"},
        }, headers=tenant_b_headers)
        assert r.status_code == 200, r.text
        return r.json()

    def test_delete_cross_tenant_blocked(self, client, tenant_a_headers, filter_in_b):
        """Tenant A cannot delete a saved filter belonging to Tenant B."""
        r = client.delete(f"/api/saved-filters/{filter_in_b['id']}",
                          headers=tenant_a_headers)
        assert r.status_code == 404

    def test_filter_still_exists_in_b(self, client, tenant_b_headers, filter_in_b):
        """Saved filter is intact in Tenant B after failed cross-tenant attempt."""
        r = client.get("/api/saved-filters", headers=tenant_b_headers)
        assert r.status_code == 200
        ids = [sf["id"] for sf in r.json()]
        assert filter_in_b["id"] in ids


# ── Custom field isolation ────────────────────────────────────────────────────

class TestCustomFieldTenantIsolation:
    """Custom field values are scoped to the requesting tenant."""

    @pytest.fixture(scope="class")
    def field_def_in_b(self, client, tenant_b_headers):
        """Create a custom field definition in Tenant B."""
        r = client.post("/api/custom-fields/defs", json={
            "label": f"Secret Field {_uid()}",
            "field_type": "text",
        }, headers=tenant_b_headers)
        assert r.status_code == 200, r.text
        return r.json()

    @pytest.fixture(scope="class")
    def asset_in_b(self, client, tenant_b_headers):
        tag = f"ISO-B-{_uid() % 999999:06d}"
        r = client.post("/api/assets", json={
            "asset_tag": tag,
            "name": "Isolation Asset B",
            "status": "available",
        }, headers=tenant_b_headers)
        assert r.status_code == 200, r.text
        return r.json()

    @pytest.fixture(scope="class")
    def asset_in_a(self, client, tenant_a_headers):
        tag = f"ISO-A-{_uid() % 999999:06d}"
        r = client.post("/api/assets", json={
            "asset_tag": tag,
            "name": "Isolation Asset A",
            "status": "available",
        }, headers=tenant_a_headers)
        assert r.status_code == 200, r.text
        return r.json()

    def test_set_custom_field_value_in_b(self, client, tenant_b_headers, field_def_in_b, asset_in_b):
        """Tenant B can set a custom field value on its own asset."""
        r = client.put(f"/api/custom-fields/values/{asset_in_b['id']}",
                       json=[{"field_def_id": field_def_in_b["id"], "value": "secret-data"}],
                       headers=tenant_b_headers)
        assert r.status_code == 200
        data = r.json()
        labels = [cf["label"] for cf in data]
        assert field_def_in_b["label"] in labels

    def test_cross_tenant_cannot_read_custom_field_values(
            self, client, tenant_a_headers, asset_in_b, field_def_in_b):
        """Tenant A cannot read Tenant B's asset or its custom fields (asset is 404)."""
        r = client.get(f"/api/custom-fields/values/{asset_in_b['id']}",
                       headers=tenant_a_headers)
        assert r.status_code == 404

    def test_cross_tenant_cannot_set_field_def_from_b_on_a_asset(
            self, client, tenant_a_headers, asset_in_a, field_def_in_b):
        """Tenant A cannot use Tenant B's field_def_id to write values on Tenant A's asset.
        The silently-skipped write means the value does not appear in the response."""
        r = client.put(f"/api/custom-fields/values/{asset_in_a['id']}",
                       json=[{"field_def_id": field_def_in_b["id"], "value": "cross-leak"}],
                       headers=tenant_a_headers)
        assert r.status_code == 200
        # The foreign field_def should have been silently skipped
        labels = [cf["label"] for cf in r.json()]
        assert field_def_in_b["label"] not in labels

    def test_b_field_values_not_visible_through_asset_detail(
            self, client, tenant_a_headers, asset_in_b):
        """Tenant B's asset detail is not accessible from Tenant A."""
        r = client.get(f"/api/assets/{asset_in_b['id']}", headers=tenant_a_headers)
        assert r.status_code == 404
