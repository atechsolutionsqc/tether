"""
test_custom_fields.py — Per-tenant custom field definitions and values.

Covers:
  - Create a field def (requires categories.manage)
  - List field defs scoped to tenant
  - Update a field def
  - Delete a field def (cascades values)
  - Upsert field values on an asset
  - Get field values for an asset
  - GET /api/assets/{id} includes custom_fields list
  - Duplicate label rejected
  - Invalid field_type rejected
  - Cross-tenant isolation: defs from tenant A not visible to tenant B
  - Auth required on all endpoints
  - CSV export includes custom field columns
"""
import io
import time
import csv as _csv

import pytest


def _tag():
    return f"CF-{int(time.time() * 1000) % 999999:06d}"


def _make_asset(client, headers):
    r = client.post("/api/assets", json={
        "asset_tag": _tag(), "name": "CF Test Asset", "status": "available",
    }, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


class TestFieldDefCRUD:
    def test_create_field_def(self, client, tenant_headers):
        r = client.post("/api/custom-fields/defs", json={
            "label": f"IMEI-{_tag()}", "field_type": "text", "required": False,
        }, headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert "id" in d
        assert d["field_type"] == "text"
        assert d["required"] is False

    def test_list_field_defs(self, client, tenant_headers):
        label = f"VLAN-{_tag()}"
        client.post("/api/custom-fields/defs", json={"label": label, "field_type": "number"},
                    headers=tenant_headers)
        r = client.get("/api/custom-fields/defs", headers=tenant_headers)
        assert r.status_code == 200
        labels = [d["label"] for d in r.json()]
        assert label in labels

    def test_update_field_def(self, client, tenant_headers):
        r = client.post("/api/custom-fields/defs", json={
            "label": f"OldLabel-{_tag()}", "field_type": "text",
        }, headers=tenant_headers)
        def_id = r.json()["id"]
        new_label = f"NewLabel-{_tag()}"
        r2 = client.put(f"/api/custom-fields/defs/{def_id}", json={
            "label": new_label, "field_type": "url", "required": True,
        }, headers=tenant_headers)
        assert r2.status_code == 200
        assert r2.json()["label"] == new_label
        assert r2.json()["field_type"] == "url"
        assert r2.json()["required"] is True

    def test_delete_field_def(self, client, tenant_headers):
        r = client.post("/api/custom-fields/defs", json={
            "label": f"ToDelete-{_tag()}", "field_type": "text",
        }, headers=tenant_headers)
        def_id = r.json()["id"]
        r2 = client.delete(f"/api/custom-fields/defs/{def_id}", headers=tenant_headers)
        assert r2.status_code == 200
        assert r2.json()["ok"] is True
        # Should no longer appear in list
        defs = client.get("/api/custom-fields/defs", headers=tenant_headers).json()
        ids = [d["id"] for d in defs]
        assert def_id not in ids

    def test_duplicate_label_rejected(self, client, tenant_headers):
        label = f"Duplicate-{_tag()}"
        client.post("/api/custom-fields/defs", json={"label": label, "field_type": "text"},
                    headers=tenant_headers)
        r2 = client.post("/api/custom-fields/defs", json={"label": label, "field_type": "number"},
                         headers=tenant_headers)
        assert r2.status_code == 400

    def test_invalid_field_type_rejected(self, client, tenant_headers):
        r = client.post("/api/custom-fields/defs", json={
            "label": f"BadType-{_tag()}", "field_type": "json",
        }, headers=tenant_headers)
        assert r.status_code == 400


class TestFieldValues:
    def test_upsert_and_get_values(self, client, tenant_headers):
        label = f"Dept-{_tag()}"
        r_def = client.post("/api/custom-fields/defs", json={"label": label, "field_type": "text"},
                            headers=tenant_headers)
        def_id = r_def.json()["id"]
        asset = _make_asset(client, tenant_headers)

        r = client.put(f"/api/custom-fields/values/{asset['id']}", json=[
            {"field_def_id": def_id, "value": "Engineering"},
        ], headers=tenant_headers)
        assert r.status_code == 200
        vals = r.json()
        assert any(v["label"] == label and v["value"] == "Engineering" for v in vals)

    def test_upsert_updates_existing_value(self, client, tenant_headers):
        label = f"Serial-{_tag()}"
        r_def = client.post("/api/custom-fields/defs", json={"label": label, "field_type": "text"},
                            headers=tenant_headers)
        def_id = r_def.json()["id"]
        asset = _make_asset(client, tenant_headers)

        client.put(f"/api/custom-fields/values/{asset['id']}",
                   json=[{"field_def_id": def_id, "value": "first"}],
                   headers=tenant_headers)
        r2 = client.put(f"/api/custom-fields/values/{asset['id']}",
                        json=[{"field_def_id": def_id, "value": "second"}],
                        headers=tenant_headers)
        assert r2.status_code == 200
        vals = r2.json()
        matching = [v for v in vals if v["label"] == label]
        assert len(matching) == 1
        assert matching[0]["value"] == "second"

    def test_get_field_values(self, client, tenant_headers):
        label = f"GetTest-{_tag()}"
        r_def = client.post("/api/custom-fields/defs", json={"label": label, "field_type": "text"},
                            headers=tenant_headers)
        def_id = r_def.json()["id"]
        asset = _make_asset(client, tenant_headers)
        client.put(f"/api/custom-fields/values/{asset['id']}",
                   json=[{"field_def_id": def_id, "value": "hello"}],
                   headers=tenant_headers)

        r = client.get(f"/api/custom-fields/values/{asset['id']}", headers=tenant_headers)
        assert r.status_code == 200
        vals = r.json()
        assert any(v["value"] == "hello" for v in vals)

    def test_asset_detail_includes_custom_fields(self, client, tenant_headers):
        label = f"LicKey-{_tag()}"
        r_def = client.post("/api/custom-fields/defs", json={"label": label, "field_type": "text"},
                            headers=tenant_headers)
        def_id = r_def.json()["id"]
        asset = _make_asset(client, tenant_headers)
        client.put(f"/api/custom-fields/values/{asset['id']}",
                   json=[{"field_def_id": def_id, "value": "XXXX-YYYY-ZZZZ"}],
                   headers=tenant_headers)

        r = client.get(f"/api/assets/{asset['id']}", headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert "custom_fields" in data
        assert any(cf["label"] == label and cf["value"] == "XXXX-YYYY-ZZZZ"
                   for cf in data["custom_fields"])

    def test_delete_def_cascades_values(self, client, tenant_headers):
        label = f"Cascade-{_tag()}"
        r_def = client.post("/api/custom-fields/defs", json={"label": label, "field_type": "text"},
                            headers=tenant_headers)
        def_id = r_def.json()["id"]
        asset = _make_asset(client, tenant_headers)
        client.put(f"/api/custom-fields/values/{asset['id']}",
                   json=[{"field_def_id": def_id, "value": "will-be-gone"}],
                   headers=tenant_headers)

        client.delete(f"/api/custom-fields/defs/{def_id}", headers=tenant_headers)

        r = client.get(f"/api/custom-fields/values/{asset['id']}", headers=tenant_headers)
        labels = [v["label"] for v in r.json()]
        assert label not in labels


class TestCrossTenantIsolation:
    def test_def_not_visible_across_tenants(self, client, auth, tenant_headers):
        # Create a second tenant
        slug2 = f"cf-isolation-{int(time.time()) % 9999}"
        r_t2 = client.post("/api/tenants", json={"name": "CF Corp 2", "slug": slug2},
                           headers=auth)
        assert r_t2.status_code == 200
        h2 = {**auth, "host": f"{slug2}.localhost"}

        # Create def in tenant 1
        label = f"T1Only-{_tag()}"
        client.post("/api/custom-fields/defs", json={"label": label, "field_type": "text"},
                    headers=tenant_headers)

        # Tenant 2 should not see it
        r = client.get("/api/custom-fields/defs", headers=h2)
        assert r.status_code == 200
        labels = [d["label"] for d in r.json()]
        assert label not in labels


class TestAuth:
    def test_list_defs_requires_auth(self, client, tenant):
        r = client.get("/api/custom-fields/defs",
                       headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401

    def test_create_def_requires_auth(self, client, tenant):
        r = client.post("/api/custom-fields/defs",
                        json={"label": "NoAuth", "field_type": "text"},
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401

    def test_upsert_values_requires_auth(self, client, tenant):
        r = client.put("/api/custom-fields/values/999",
                       json=[{"field_def_id": 1, "value": "x"}],
                       headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestCSVExport:
    def test_csv_export_includes_custom_field_columns(self, client, tenant_headers):
        label = f"ExportField-{_tag()}"
        r_def = client.post("/api/custom-fields/defs", json={"label": label, "field_type": "text"},
                            headers=tenant_headers)
        def_id = r_def.json()["id"]
        asset = _make_asset(client, tenant_headers)
        client.put(f"/api/custom-fields/values/{asset['id']}",
                   json=[{"field_def_id": def_id, "value": "export-value"}],
                   headers=tenant_headers)

        r = client.get("/api/assets/export/csv", headers=tenant_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]

        reader = _csv.DictReader(io.StringIO(r.text))
        assert label in (reader.fieldnames or []), \
            f"Expected column '{label}' in CSV headers: {reader.fieldnames}"

        rows = list(reader)
        matching = [row for row in rows if row.get("asset_tag") == asset["asset_tag"]]
        assert matching, "Asset not found in CSV"
        assert matching[0].get(label) == "export-value"
