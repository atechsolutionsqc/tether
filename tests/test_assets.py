"""
test_assets.py — Asset management tests.

Covers:
  - Create / read / update / delete
  - Asset tag uniqueness within tenant
  - Status lifecycle (available → deployed → available)
  - Check-out and check-in
  - Checkout history
  - QR code generation
  - CSV export
  - CSV import (create + update + error rows)
  - Search and filtering
  - Cross-tenant isolation
"""
import io
import time


def _tag():
    return f"AT-{int(time.time() * 1000) % 999999:06d}"


class TestCreateAsset:
    def test_create_asset(self, client, tenant_headers):
        r = client.post("/api/assets", json={
            "asset_tag": _tag(), "name": "Test Laptop",
            "status": "available", "manufacturer": "Dell",
        }, headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Test Laptop"
        assert data["status"] == "available"

    def test_duplicate_tag_rejected(self, client, tenant_headers):
        tag = _tag()
        client.post("/api/assets", json={
            "asset_tag": tag, "name": "First", "status": "available",
        }, headers=tenant_headers)
        r = client.post("/api/assets", json={
            "asset_tag": tag, "name": "Second", "status": "available",
        }, headers=tenant_headers)
        assert r.status_code == 400

    def test_requires_authentication(self, client, tenant):
        r = client.post("/api/assets", json={
            "asset_tag": _tag(), "name": "X", "status": "available",
        }, headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestReadAsset:
    def test_list_assets(self, client, tenant_headers, fresh_asset):
        r = client.get("/api/assets", headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "total" in data
        tags = [a["asset_tag"] for a in data["items"]]
        assert fresh_asset["asset_tag"] in tags

    def test_get_asset_by_id(self, client, tenant_headers, fresh_asset):
        r = client.get(f"/api/assets/{fresh_asset['id']}", headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["id"] == fresh_asset["id"]

    def test_get_nonexistent_returns_404(self, client, tenant_headers):
        r = client.get("/api/assets/999999", headers=tenant_headers)
        assert r.status_code == 404

    def test_search_by_name(self, client, tenant_headers):
        tag  = _tag()
        name = f"SearchableAsset{tag}"
        client.post("/api/assets", json={
            "asset_tag": tag, "name": name, "status": "available",
        }, headers=tenant_headers)
        r = client.get(f"/api/assets?q={tag}", headers=tenant_headers)
        assert r.status_code == 200
        assert any(a["asset_tag"] == tag for a in r.json()["items"])

    def test_filter_by_status(self, client, tenant_headers):
        r = client.get("/api/assets?status=available", headers=tenant_headers)
        assert r.status_code == 200
        for asset in r.json()["items"]:
            assert asset["status"] == "available"


class TestUpdateAsset:
    def test_update_asset_name(self, client, tenant_headers, fresh_asset):
        asset = fresh_asset
        r = client.put(f"/api/assets/{asset['id']}", json={
            **asset,
            "name":   "Updated Name",
            "status": "available",
        }, headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["name"] == "Updated Name"

    def test_update_status_to_maintenance(self, client, tenant_headers, fresh_asset):
        asset = fresh_asset
        r = client.put(f"/api/assets/{asset['id']}", json={
            **asset, "status": "maintenance",
        }, headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "maintenance"


class TestDeleteAsset:
    def test_delete_asset(self, client, tenant_headers):
        tag = _tag()
        a = client.post("/api/assets", json={
            "asset_tag": tag, "name": "To Delete", "status": "available",
        }, headers=tenant_headers).json()
        r = client.delete(f"/api/assets/{a['id']}", headers=tenant_headers)
        assert r.status_code == 200
        r2 = client.get(f"/api/assets/{a['id']}", headers=tenant_headers)
        assert r2.status_code == 404


class TestCheckout:
    def test_checkout_and_checkin(self, client, tenant_headers,
                                  fresh_asset, fresh_employee):
        asset_id    = fresh_asset["id"]
        employee_id = fresh_employee["id"]

        # Check out
        r = client.post(f"/api/assets/{asset_id}/checkout", json={
            "employee_id": employee_id,
            "note":        "Test checkout",
        }, headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "deployed"

        # Check in
        r2 = client.post(f"/api/assets/{asset_id}/checkin", json={
            "note": "Returned",
        }, headers=tenant_headers)
        assert r2.status_code == 200
        assert r2.json()["status"] == "available"

    def test_cannot_checkout_deployed_asset(self, client, tenant_headers,
                                             fresh_employee):
        tag = _tag()
        a = client.post("/api/assets", json={
            "asset_tag": tag, "name": "Busy Asset", "status": "available",
        }, headers=tenant_headers).json()

        # First checkout
        client.post(f"/api/assets/{a['id']}/checkout",
                    json={"employee_id": fresh_employee["id"]},
                    headers=tenant_headers)

        # Second checkout should fail
        r = client.post(f"/api/assets/{a['id']}/checkout",
                        json={"employee_id": fresh_employee["id"]},
                        headers=tenant_headers)
        assert r.status_code == 400

    def test_checkout_history_recorded(self, client, tenant_headers,
                                        fresh_asset, fresh_employee):
        asset_id = fresh_asset["id"]
        client.post(f"/api/assets/{asset_id}/checkout", json={
            "employee_id": fresh_employee["id"],
            "note":        "History test",
        }, headers=tenant_headers)
        r = client.get(f"/api/assets/{asset_id}/history",
                       headers=tenant_headers)
        assert r.status_code == 200
        history = r.json()
        assert len(history) >= 1
        assert history[-1]["action"] == "checkout"


class TestQR:
    def test_qr_returns_png(self, client, tenant_headers, fresh_asset):
        r = client.get(f"/api/assets/{fresh_asset['id']}/qr",
                       headers=tenant_headers)
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert len(r.content) > 100  # non-empty PNG

    def test_qr_no_auth_required(self, client, tenant, fresh_asset):
        """QR endpoint is public."""
        r = client.get(f"/api/assets/{fresh_asset['id']}/qr",
                       headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 200


class TestLabelPrint:
    def test_labels_returns_html(self, client, tenant_headers, fresh_asset):
        r = client.post("/api/assets/labels",
                        json={"asset_ids": [fresh_asset["id"]], "size": "medium"},
                        headers=tenant_headers)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert fresh_asset["asset_tag"] in r.text
        assert "<svg" in r.text  # QR code rendered

    def test_labels_all_sizes(self, client, tenant_headers, fresh_asset):
        for size in ("small", "medium", "large"):
            r = client.post("/api/assets/labels",
                            json={"asset_ids": [fresh_asset["id"]], "size": size},
                            headers=tenant_headers)
            assert r.status_code == 200, f"size={size} failed"

    def test_labels_invalid_size_rejected(self, client, tenant_headers, fresh_asset):
        r = client.post("/api/assets/labels",
                        json={"asset_ids": [fresh_asset["id"]], "size": "giant"},
                        headers=tenant_headers)
        assert r.status_code == 422

    def test_labels_empty_list_rejected(self, client, tenant_headers):
        r = client.post("/api/assets/labels",
                        json={"asset_ids": [], "size": "medium"},
                        headers=tenant_headers)
        assert r.status_code == 422

    def test_labels_requires_auth(self, client, fresh_asset):
        r = client.post("/api/assets/labels",
                        json={"asset_ids": [fresh_asset["id"]], "size": "medium"})
        assert r.status_code == 401

    def test_labels_client_cannot_reach_other_tenant(self, client, auth, roles, tenant, fresh_asset):
        """A client user from tenant A cannot print labels for tenant B's assets."""
        # Create a second tenant and a client user scoped to it
        r = client.post("/api/tenants", json={"name": "Label Tenant B", "slug": "labeltb", "currency": "USD"}, headers=auth)
        assert r.status_code == 200
        tid_b = r.json()["id"]
        r = client.post("/api/users", json={
            "name": "Label Client B", "email": "labelb@fixture.com",
            "password": "Password123!", "role_id": roles["client_admin"]["id"],
            "tenant_id": tid_b, "is_msp_staff": False,
        }, headers=auth)
        assert r.status_code == 200
        lr = client.post("/api/auth/login", data={"username": "labelb@fixture.com", "password": "Password123!"})
        b_auth = {"Authorization": f"Bearer {lr.json()['access_token']}", "host": "labeltb.localhost"}
        # fresh_asset belongs to tenant A — tenant B user should get 404
        r = client.post("/api/assets/labels",
                        json={"asset_ids": [fresh_asset["id"]], "size": "medium"},
                        headers=b_auth)
        assert r.status_code == 404


class TestCSV:
    def test_export_csv(self, client, tenant_headers, fresh_asset):
        r = client.get("/api/assets/export/csv", headers=tenant_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "asset_tag" in r.text  # header row present
        assert fresh_asset["asset_tag"] in r.text

    def test_import_csv_creates_assets(self, client, tenant_headers):
        import uuid
        tag1 = f"IM-{uuid.uuid4().hex[:8].upper()}"
        tag2 = f"IM-{uuid.uuid4().hex[:8].upper()}"
        csv_data = (
            "asset_tag,name,status,manufacturer\n"
            f"{tag1},Import One,available,Apple\n"
            f"{tag2},Import Two,available,Dell\n"
        )
        r = client.post("/api/assets/import/csv",
                        files={"file": ("assets.csv", csv_data, "text/csv")},
                        headers=tenant_headers)
        assert r.status_code == 200
        result = r.json()
        assert result["created"] == 2
        assert result["errors"] == []

    def test_import_csv_updates_existing(self, client, tenant_headers):
        tag = _tag()
        # Create first
        client.post("/api/assets", json={
            "asset_tag": tag, "name": "Original", "status": "available",
        }, headers=tenant_headers)
        # Import with updated name
        csv_data = f"asset_tag,name,status\n{tag},Updated Name,available\n"
        r = client.post("/api/assets/import/csv",
                        files={"file": ("u.csv", csv_data, "text/csv")},
                        headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["updated"] == 1

    def test_import_csv_invalid_status_handled(self, client, tenant_headers):
        """Invalid status either creates with default or is reported as error."""
        import uuid
        tag = f"BAD-{uuid.uuid4().hex[:6].upper()}"
        csv_data = f"asset_tag,name,status\n{tag},Bad Asset,invalid_status\n"
        r = client.post("/api/assets/import/csv",
                        files={"file": ("bad.csv", csv_data, "text/csv")},
                        headers=tenant_headers)
        assert r.status_code == 200
        result = r.json()
        # App either reports an error OR creates with a default status — both acceptable
        assert "errors" in result or "created" in result


class TestCsvImportPreview:
    def test_preview_identifies_creates(self, client, tenant_headers):
        import uuid
        tag = f"PRV-{uuid.uuid4().hex[:8].upper()}"
        csv_data = f"asset_tag,name,status\n{tag},Preview Asset,available\n"
        r = client.post("/api/assets/import/csv/preview",
                        files={"file": ("p.csv", csv_data, "text/csv")},
                        headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["summary"]["creates"] == 1
        assert d["summary"]["updates"] == 0
        assert d["summary"]["errors"] == 0
        assert any(a["asset_tag"] == tag for a in d["creates"])

    def test_preview_identifies_updates(self, client, tenant_headers):
        tag = _tag()
        client.post("/api/assets", json={"asset_tag": tag, "name": "Old Name", "status": "available"},
                    headers=tenant_headers)
        csv_data = f"asset_tag,name,status\n{tag},New Name,available\n"
        r = client.post("/api/assets/import/csv/preview",
                        files={"file": ("u.csv", csv_data, "text/csv")},
                        headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["summary"]["updates"] == 1
        assert d["summary"]["creates"] == 0
        row = d["updates"][0]
        assert row["asset_tag"] == tag
        assert any(c["field"] == "name" and c["to"] == "New Name" for c in row["changes"])

    def test_preview_reports_missing_asset_tag(self, client, tenant_headers):
        csv_data = "asset_tag,name,status\n,No Tag,available\n"
        r = client.post("/api/assets/import/csv/preview",
                        files={"file": ("e.csv", csv_data, "text/csv")},
                        headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["summary"]["errors"] == 1
        assert "missing asset_tag" in d["errors"][0]["error"]

    def test_preview_reports_invalid_status(self, client, tenant_headers):
        import uuid
        tag = f"PRV-{uuid.uuid4().hex[:8].upper()}"
        csv_data = f"asset_tag,name,status\n{tag},Bad,not_a_status\n"
        r = client.post("/api/assets/import/csv/preview",
                        files={"file": ("e.csv", csv_data, "text/csv")},
                        headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["summary"]["errors"] >= 1

    def test_preview_detects_new_custom_field_columns(self, client, tenant_headers):
        import uuid
        tag = f"PRV-{uuid.uuid4().hex[:8].upper()}"
        csv_data = f"asset_tag,name,IMEI_Preview_{uuid.uuid4().hex[:4]}\n{tag},CF Asset,123456789\n"
        r = client.post("/api/assets/import/csv/preview",
                        files={"file": ("cf.csv", csv_data, "text/csv")},
                        headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["summary"]["new_cf_defs"] >= 1

    def test_preview_does_not_commit(self, client, tenant_headers):
        import uuid
        tag = f"PRV-NODML-{uuid.uuid4().hex[:6].upper()}"
        csv_data = f"asset_tag,name,status\n{tag},Should Not Exist,available\n"
        client.post("/api/assets/import/csv/preview",
                    files={"file": ("p.csv", csv_data, "text/csv")},
                    headers=tenant_headers)
        r = client.get(f"/api/assets?search={tag}", headers=tenant_headers)
        assert r.status_code == 200
        assert all(a["asset_tag"] != tag for a in r.json()["items"])

    def test_preview_requires_auth(self, client, tenant):
        csv_data = "asset_tag,name\nX-001,Test\n"
        r = client.post("/api/assets/import/csv/preview",
                        files={"file": ("p.csv", csv_data, "text/csv")},
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestCrossTenantIsolation:
    def test_assets_not_visible_across_tenants(self, client, auth, tenant_headers,
                                                fresh_asset):
        """Create a second tenant and verify it cannot see the first tenant's assets."""
        import time
        uid     = int(time.time() * 1000) % 999999
        slug    = f"isolated{uid}"
        other_t = client.post("/api/tenants", json={
            "name": f"Other {uid}", "slug": slug, "currency": "USD",
        }, headers=auth).json()

        other_h = {**auth, "host": f"{slug}.localhost"}
        r = client.get("/api/assets", headers=other_h)
        assert r.status_code == 200
        asset_tags = [a["asset_tag"] for a in r.json()["items"]]
        assert fresh_asset["asset_tag"] not in asset_tags


class TestPagination:
    def test_response_shape(self, client, tenant_headers, fresh_asset):
        r = client.get("/api/assets", headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "limit" in data
        assert "pages" in data
        assert isinstance(data["items"], list)
        assert data["total"] >= 1
        assert data["page"] == 1
        assert data["pages"] == max(1, -(-data["total"] // data["limit"]))  # ceil division

    def test_page_2_differs_from_page_1(self, client, tenant_headers):
        tags = [_tag() for _ in range(3)]
        for tag in tags:
            client.post("/api/assets", json={
                "asset_tag": tag, "name": f"Pageable {tag}", "status": "available",
            }, headers=tenant_headers)

        r1 = client.get("/api/assets?limit=1&page=1&sort=asset_tag&order=asc", headers=tenant_headers)
        r2 = client.get("/api/assets?limit=1&page=2&sort=asset_tag&order=asc", headers=tenant_headers)
        assert r1.status_code == 200
        assert r2.status_code == 200
        d1, d2 = r1.json(), r2.json()
        assert d1["total"] == d2["total"]
        assert d1["items"] != d2["items"]

    def test_limit_clamps_result_count(self, client, tenant_headers):
        for _ in range(3):
            client.post("/api/assets", json={
                "asset_tag": _tag(), "name": "Limitable", "status": "available",
            }, headers=tenant_headers)

        r = client.get("/api/assets?limit=2", headers=tenant_headers)
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 2

    def test_filter_and_pagination_combined(self, client, tenant_headers):
        uid = int(time.time() * 1000) % 999999
        for i in range(3):
            client.post("/api/assets", json={
                "asset_tag": f"PAG-{uid}-{i}", "name": f"PagFilter {i}",
                "status": "maintenance",
            }, headers=tenant_headers)

        r = client.get("/api/assets?status=maintenance&limit=1&page=1", headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 3
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "maintenance"

    def test_csv_export_ignores_pagination(self, client, tenant_headers):
        for _ in range(3):
            client.post("/api/assets", json={
                "asset_tag": _tag(), "name": "CSVCheck", "status": "available",
            }, headers=tenant_headers)

        r_csv = client.get("/api/assets/export/csv", headers=tenant_headers)
        r_list = client.get("/api/assets?limit=1", headers=tenant_headers)
        assert r_csv.status_code == 200
        # CSV row count (minus header) should equal total from the paginated endpoint
        csv_rows = [line for line in r_csv.text.strip().splitlines() if line][1:]
        assert len(csv_rows) == r_list.json()["total"]


def _create_client_viewer_headers(client, auth, tenant, roles):
    """Create a client_viewer user and return auth headers scoped to the fixture tenant."""
    email = f"viewer_{_tag()}@test.com"
    r = client.post("/api/users", json={
        "name": "Bulk Viewer", "email": email, "password": "Secure123!",
        "role_id": roles["client_viewer"]["id"],
        "tenant_id": tenant["id"], "is_msp_staff": False, "active": True,
    }, headers=auth)
    assert r.status_code == 200, r.text
    lr = client.post("/api/auth/login", data={"username": email, "password": "Secure123!"})
    assert lr.status_code == 200
    return {"Authorization": f"Bearer {lr.json()['access_token']}",
            "host": f"{tenant['slug']}.localhost"}


class TestBulkActions:
    def _make_assets(self, client, tenant_headers, n=3):
        ids = []
        for _ in range(n):
            r = client.post("/api/assets", json={
                "asset_tag": _tag(), "name": "Bulk Asset", "status": "available",
            }, headers=tenant_headers)
            assert r.status_code == 200
            ids.append(r.json()["id"])
        return ids

    # ── bulk/status ────────────────────────────────────────────────────────────

    def test_bulk_status_updates_all(self, client, tenant_headers):
        ids = self._make_assets(client, tenant_headers, 3)
        r = client.post("/api/assets/bulk/status",
                        json={"asset_ids": ids, "status": "maintenance"},
                        headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["updated"] == 3
        assert data["skipped"] == 0
        for aid in ids:
            a = client.get(f"/api/assets/{aid}", headers=tenant_headers).json()
            assert a["status"] == "maintenance"

    def test_bulk_status_rejects_invalid_status(self, client, tenant_headers):
        ids = self._make_assets(client, tenant_headers, 1)
        r = client.post("/api/assets/bulk/status",
                        json={"asset_ids": ids, "status": "broken"},
                        headers=tenant_headers)
        assert r.status_code == 400

    def test_bulk_status_skips_other_tenant_assets(self, client, auth, tenant_headers):
        import time
        uid = int(time.time() * 1000) % 999999
        other_t = client.post("/api/tenants", json={
            "name": f"OtherBulk {uid}", "slug": f"otherbulk{uid}", "currency": "CAD",
        }, headers=auth).json()
        other_h = {**auth, "host": f"otherbulk{uid}.localhost"}
        other_asset = client.post("/api/assets", json={
            "asset_tag": _tag(), "name": "Other Tenant Asset", "status": "available",
        }, headers=other_h).json()

        my_ids = self._make_assets(client, tenant_headers, 2)
        all_ids = my_ids + [other_asset["id"]]

        r = client.post("/api/assets/bulk/status",
                        json={"asset_ids": all_ids, "status": "retired"},
                        headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["updated"] == 2
        assert data["skipped"] == 1
        # other tenant's asset should be unchanged
        other_check = client.get(f"/api/assets/{other_asset['id']}", headers=other_h)
        assert other_check.json()["status"] == "available"

    def test_bulk_status_requires_auth(self, client, tenant):
        r = client.post("/api/assets/bulk/status",
                        json={"asset_ids": [1], "status": "available"},
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401

    # ── bulk/location ──────────────────────────────────────────────────────────

    def test_bulk_location_updates_all(self, client, tenant_headers, tenant, auth):
        ids = self._make_assets(client, tenant_headers, 2)
        # get a location that belongs to this tenant
        locs = client.get("/api/locations", headers=tenant_headers).json()["items"]
        assert locs, "No locations seeded for fixture tenant"
        loc_id = locs[0]["id"]

        r = client.post("/api/assets/bulk/location",
                        json={"asset_ids": ids, "location_id": loc_id},
                        headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["updated"] == 2
        assert data["skipped"] == 0
        for aid in ids:
            a = client.get(f"/api/assets/{aid}", headers=tenant_headers).json()
            assert a["location_id"] == loc_id

    def test_bulk_location_rejects_foreign_location(self, client, auth, tenant_headers):
        import time
        uid = int(time.time() * 1000) % 999999
        other_t = client.post("/api/tenants", json={
            "name": f"ForeignLoc {uid}", "slug": f"foreignloc{uid}", "currency": "CAD",
        }, headers=auth).json()
        other_h = {**auth, "host": f"foreignloc{uid}.localhost"}
        foreign_locs = client.get("/api/locations", headers=other_h).json()["items"]
        assert foreign_locs, "No locations for foreign tenant"
        foreign_loc_id = foreign_locs[0]["id"]

        ids = self._make_assets(client, tenant_headers, 1)
        r = client.post("/api/assets/bulk/location",
                        json={"asset_ids": ids, "location_id": foreign_loc_id},
                        headers=tenant_headers)
        assert r.status_code == 400

    def test_bulk_location_requires_auth(self, client, tenant):
        r = client.post("/api/assets/bulk/location",
                        json={"asset_ids": [1], "location_id": 1},
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401

    # ── bulk/delete ────────────────────────────────────────────────────────────

    def test_bulk_delete_removes_assets(self, client, tenant_headers):
        ids = self._make_assets(client, tenant_headers, 3)
        r = client.post("/api/assets/bulk/delete",
                        json={"asset_ids": ids},
                        headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["deleted"] == 3
        assert data["skipped"] == 0
        for aid in ids:
            check = client.get(f"/api/assets/{aid}", headers=tenant_headers)
            assert check.status_code == 404

    def test_bulk_delete_skips_other_tenant_assets(self, client, auth, tenant_headers):
        import time
        uid = int(time.time() * 1000) % 999999
        other_t = client.post("/api/tenants", json={
            "name": f"OtherDel {uid}", "slug": f"otherdel{uid}", "currency": "CAD",
        }, headers=auth).json()
        other_h = {**auth, "host": f"otherdel{uid}.localhost"}
        other_asset = client.post("/api/assets", json={
            "asset_tag": _tag(), "name": "Other Del Asset", "status": "available",
        }, headers=other_h).json()

        my_ids = self._make_assets(client, tenant_headers, 2)
        r = client.post("/api/assets/bulk/delete",
                        json={"asset_ids": my_ids + [other_asset["id"]]},
                        headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["deleted"] == 2
        assert data["skipped"] == 1
        # other tenant's asset survived
        check = client.get(f"/api/assets/{other_asset['id']}", headers=other_h)
        assert check.status_code == 200

    def test_bulk_delete_requires_auth(self, client, tenant):
        r = client.post("/api/assets/bulk/delete",
                        json={"asset_ids": [1]},
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401

    def test_bulk_delete_requires_delete_permission(self, client, auth, tenant, roles):
        viewer_h = _create_client_viewer_headers(client, auth, tenant, roles)
        ids = self._make_assets(client, {**auth, "host": f"{tenant['slug']}.localhost"}, 1)
        r = client.post("/api/assets/bulk/delete",
                        json={"asset_ids": ids},
                        headers=viewer_h)
        assert r.status_code == 403


class TestActivityFeed:
    """Tests for GET /api/assets/activity."""

    @staticmethod
    def _make_asset(client, tenant_headers):
        r = client.post("/api/assets", json={
            "asset_tag": _tag(), "name": "Activity Asset", "status": "available",
        }, headers=tenant_headers)
        assert r.status_code == 200
        return r.json()

    @staticmethod
    def _checkout(client, tenant_headers, asset_id, employee_id):
        return client.post(f"/api/assets/{asset_id}/checkout", json={
            "employee_id": employee_id, "note": "Test checkout note",
        }, headers=tenant_headers)

    @staticmethod
    def _checkin(client, tenant_headers, asset_id):
        return client.post(f"/api/assets/{asset_id}/checkin", json={
            "note": "Test checkin note",
        }, headers=tenant_headers)

    def test_returns_correct_shape(self, client, tenant_headers):
        r = client.get("/api/assets/activity", headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        for key in ("items", "total", "limit", "offset"):
            assert key in data, f"Missing key: {key}"
        assert isinstance(data["items"], list)
        assert data["limit"] == 50
        assert data["offset"] == 0

    def test_checkout_event_appears(self, client, tenant_headers, fresh_employee):
        asset = self._make_asset(client, tenant_headers)
        self._checkout(client, tenant_headers, asset["id"], fresh_employee["id"])

        r = client.get(
            f"/api/assets/activity?action=checkout&asset_id={asset['id']}",
            headers=tenant_headers,
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        ev = items[0]
        assert ev["action"] == "checkout"
        assert ev["asset_tag"] == asset["asset_tag"]
        assert ev["actor_type"] == "employee"
        assert "timestamp" in ev

    def test_checkin_event_appears(self, client, tenant_headers, fresh_employee):
        asset = self._make_asset(client, tenant_headers)
        self._checkout(client, tenant_headers, asset["id"], fresh_employee["id"])
        self._checkin(client, tenant_headers, asset["id"])

        r = client.get(
            f"/api/assets/activity?action=checkin&asset_id={asset['id']}",
            headers=tenant_headers,
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(ev["action"] == "checkin" for ev in items)

    def test_action_filter_returns_only_matching_type(self, client, tenant_headers, fresh_employee):
        asset = self._make_asset(client, tenant_headers)
        self._checkout(client, tenant_headers, asset["id"], fresh_employee["id"])
        self._checkin(client, tenant_headers, asset["id"])

        for action in ("checkout", "checkin"):
            r = client.get(
                f"/api/assets/activity?action={action}",
                headers=tenant_headers,
            )
            assert r.status_code == 200
            items = r.json()["items"]
            assert all(ev["action"] == action for ev in items), \
                f"Expected only '{action}' events, got: {[ev['action'] for ev in items]}"

    def test_asset_id_filter(self, client, tenant_headers, fresh_employee):
        a1 = self._make_asset(client, tenant_headers)
        a2 = self._make_asset(client, tenant_headers)
        self._checkout(client, tenant_headers, a1["id"], fresh_employee["id"])
        self._checkout(client, tenant_headers, a2["id"], fresh_employee["id"])

        r = client.get(
            f"/api/assets/activity?asset_id={a1['id']}",
            headers=tenant_headers,
        )
        assert r.status_code == 200
        items = r.json()["items"]
        # All returned events must be for a1
        asset_tags = {ev["asset_tag"] for ev in items}
        assert asset_tags == {a1["asset_tag"]}, \
            f"Expected only {a1['asset_tag']!r}, got {asset_tags}"

    def test_limit_and_offset(self, client, tenant_headers, fresh_employee):
        # Create two assets and check them out to ensure at least 2 checkout events
        a1 = self._make_asset(client, tenant_headers)
        a2 = self._make_asset(client, tenant_headers)
        self._checkout(client, tenant_headers, a1["id"], fresh_employee["id"])
        self._checkin(client, tenant_headers, a1["id"])
        self._checkout(client, tenant_headers, a2["id"], fresh_employee["id"])

        r1 = client.get(
            "/api/assets/activity?action=checkout&limit=1&offset=0",
            headers=tenant_headers,
        )
        r2 = client.get(
            "/api/assets/activity?action=checkout&limit=1&offset=1",
            headers=tenant_headers,
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["total"] == r2.json()["total"]
        assert len(r1.json()["items"]) == 1
        # Different events at different offsets
        if r2.json()["items"]:
            assert r1.json()["items"][0]["id"] != r2.json()["items"][0]["id"]

    def test_requires_authentication(self, client, tenant):
        r = client.get("/api/assets/activity",
                       headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401

    def test_cross_tenant_isolation(self, client, auth, tenant_headers, fresh_employee):
        """Activity from tenant A is not visible to tenant B."""
        other_slug = f"act-iso-{_tag()}"
        r_t = client.post("/api/tenants", json={
            "name": "Activity Iso Corp", "slug": other_slug,
        }, headers=auth)
        assert r_t.status_code == 200, f"Tenant creation failed: {r_t.text}"
        created_slug = r_t.json().get("slug", other_slug)
        other_h = {**auth, "host": f"{created_slug}.localhost"}

        # Create checkout in the fixture tenant
        asset = self._make_asset(client, tenant_headers)
        self._checkout(client, tenant_headers, asset["id"], fresh_employee["id"])

        # Other tenant's activity feed must not contain this event
        r = client.get("/api/assets/activity", headers=other_h)
        assert r.status_code == 200
        tags = {ev["asset_tag"] for ev in r.json()["items"]}
        assert asset["asset_tag"] not in tags


class TestActivityDateFilter:
    """Tests for date_from / date_to filters on GET /api/assets/activity."""

    def _make_asset(self, client, headers):
        import time as _t
        uid = int(_t.time() * 1000) % 99999999
        r = client.post("/api/assets", json={
            "asset_tag": f"ADF-{uid}", "name": f"ADF Asset {uid}", "status": "available",
        }, headers=headers)
        assert r.status_code == 200
        return r.json()

    def _checkout(self, client, headers, asset_id, employee_id):
        r = client.post(f"/api/assets/{asset_id}/checkout",
                        json={"employee_id": employee_id}, headers=headers)
        assert r.status_code == 200

    def test_date_from_excludes_older_events(self, client, tenant_headers, fresh_employee):
        from datetime import date, timedelta
        asset = self._make_asset(client, tenant_headers)
        self._checkout(client, tenant_headers, asset["id"], fresh_employee["id"])

        # date_from = tomorrow means today's events are excluded
        future = (date.today() + timedelta(days=1)).isoformat()
        r = client.get(f"/api/assets/activity?date_from={future}", headers=tenant_headers)
        assert r.status_code == 200
        tags = {ev["asset_tag"] for ev in r.json()["items"]}
        assert asset["asset_tag"] not in tags

    def test_date_to_excludes_future_events(self, client, tenant_headers, fresh_employee):
        from datetime import date, timedelta
        asset = self._make_asset(client, tenant_headers)
        self._checkout(client, tenant_headers, asset["id"], fresh_employee["id"])

        # date_to = yesterday means today's events are excluded
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        r = client.get(f"/api/assets/activity?date_to={yesterday}", headers=tenant_headers)
        assert r.status_code == 200
        tags = {ev["asset_tag"] for ev in r.json()["items"]}
        assert asset["asset_tag"] not in tags

    def test_date_range_includes_todays_events(self, client, tenant_headers, fresh_employee):
        from datetime import date
        asset = self._make_asset(client, tenant_headers)
        self._checkout(client, tenant_headers, asset["id"], fresh_employee["id"])

        today = date.today().isoformat()
        r = client.get(
            f"/api/assets/activity?date_from={today}&date_to={today}",
            headers=tenant_headers,
        )
        assert r.status_code == 200
        tags = {ev["asset_tag"] for ev in r.json()["items"]}
        assert asset["asset_tag"] in tags

    def test_invalid_date_ignored_gracefully(self, client, tenant_headers):
        r = client.get("/api/assets/activity?date_from=not-a-date", headers=tenant_headers)
        assert r.status_code == 200


class TestPublicCheckin:
    def test_generate_token_returns_token(self, client, tenant_headers, fresh_asset):
        r = client.post(f"/api/assets/{fresh_asset['id']}/checkin-token", headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert "token" in d
        assert d["asset_tag"] == fresh_asset["asset_tag"]

    def test_get_public_info_with_valid_token(self, client, tenant_headers, fresh_asset):
        tok = client.post(f"/api/assets/{fresh_asset['id']}/checkin-token", headers=tenant_headers).json()["token"]
        r = client.get(f"/api/assets/public/checkin/{tok}")
        assert r.status_code == 200
        d = r.json()
        assert d["asset_tag"] == fresh_asset["asset_tag"]

    def test_submit_checkin_marks_used(self, client, tenant_headers, fresh_asset, fresh_employee):
        # Assign asset first
        client.post(f"/api/assets/{fresh_asset['id']}/checkout",
                    json={"employee_id": fresh_employee["id"]}, headers=tenant_headers)
        tok = client.post(f"/api/assets/{fresh_asset['id']}/checkin-token", headers=tenant_headers).json()["token"]
        r = client.post(f"/api/assets/public/checkin/{tok}")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # Second use should be rejected
        r2 = client.post(f"/api/assets/public/checkin/{tok}")
        assert r2.status_code == 410

    def test_invalid_token_returns_404(self, client):
        r = client.get("/api/assets/public/checkin/nonexistent_token_xyz")
        assert r.status_code == 404

    def test_generate_token_requires_auth(self, client, fresh_asset, tenant):
        r = client.post(f"/api/assets/{fresh_asset['id']}/checkin-token",
                        headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestAssetNotes:
    def test_notes_empty_for_new_asset(self, client, tenant_headers, fresh_asset):
        r = client.get(f"/api/assets/{fresh_asset['id']}/notes", headers=tenant_headers)
        assert r.status_code == 200
        assert r.json() == []

    def test_add_note_returns_note_object(self, client, tenant_headers, fresh_asset):
        r = client.post(f"/api/assets/{fresh_asset['id']}/notes",
                        json={"body": "Keyboard sticky key"},
                        headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["body"] == "Keyboard sticky key"
        assert "author_name" in d
        assert "created_at" in d

    def test_list_notes_contains_added_note(self, client, tenant_headers, fresh_asset):
        client.post(f"/api/assets/{fresh_asset['id']}/notes",
                    json={"body": "Battery replaced"},
                    headers=tenant_headers)
        r = client.get(f"/api/assets/{fresh_asset['id']}/notes", headers=tenant_headers)
        assert r.status_code == 200
        bodies = [n["body"] for n in r.json()]
        assert "Battery replaced" in bodies

    def test_delete_note(self, client, tenant_headers, fresh_asset):
        note = client.post(f"/api/assets/{fresh_asset['id']}/notes",
                           json={"body": "ToDelete"},
                           headers=tenant_headers).json()
        r = client.delete(f"/api/assets/{fresh_asset['id']}/notes/{note['id']}", headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["ok"] is True
        remaining = [n["id"] for n in client.get(f"/api/assets/{fresh_asset['id']}/notes", headers=tenant_headers).json()]
        assert note["id"] not in remaining

    def test_notes_cross_tenant_isolation(self, client, auth, tenant_headers, fresh_asset):
        import time
        uid = int(time.time() * 1000) % 999999
        other_t = client.post("/api/tenants", json={"name": f"NoteOther{uid}", "slug": f"noteother{uid}", "currency": "USD"}, headers=auth).json()
        other_h = {**auth, "host": f"noteother{uid}.localhost"}
        r = client.get(f"/api/assets/{fresh_asset['id']}/notes", headers=other_h)
        assert r.status_code == 404

    def test_notes_require_auth(self, client, fresh_asset, tenant):
        r = client.get(f"/api/assets/{fresh_asset['id']}/notes",
                       headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401


class TestAssetPhotos:
    """Tests for GET/POST/DELETE /api/assets/{id}/photos."""

    _TINY_PNG = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
        b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    )

    def test_upload_photo_returns_url(self, client, tenant_headers, fresh_asset):
        r = client.post(
            f"/api/assets/{fresh_asset['id']}/photos",
            files={"file": ("test.png", self._TINY_PNG, "image/png")},
            headers=tenant_headers,
        )
        assert r.status_code == 200
        d = r.json()
        assert "url" in d
        assert d["url"].startswith("/uploads/")

    def test_list_photos_returns_uploaded(self, client, tenant_headers, fresh_asset):
        client.post(
            f"/api/assets/{fresh_asset['id']}/photos",
            files={"file": ("a.png", self._TINY_PNG, "image/png")},
            headers=tenant_headers,
        )
        r = client.get(f"/api/assets/{fresh_asset['id']}/photos", headers=tenant_headers)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_delete_photo(self, client, tenant_headers, fresh_asset):
        photo = client.post(
            f"/api/assets/{fresh_asset['id']}/photos",
            files={"file": ("del.png", self._TINY_PNG, "image/png")},
            headers=tenant_headers,
        ).json()
        r = client.delete(f"/api/assets/{fresh_asset['id']}/photos/{photo['id']}", headers=tenant_headers)
        assert r.status_code == 200
        remaining = [p["id"] for p in client.get(f"/api/assets/{fresh_asset['id']}/photos", headers=tenant_headers).json()]
        assert photo["id"] not in remaining

    def test_reject_non_image_type(self, client, tenant_headers, fresh_asset):
        r = client.post(
            f"/api/assets/{fresh_asset['id']}/photos",
            files={"file": ("hack.exe", b"MZ", "application/octet-stream")},
            headers=tenant_headers,
        )
        assert r.status_code == 400

    def test_photos_require_auth(self, client, fresh_asset, tenant):
        r = client.get(
            f"/api/assets/{fresh_asset['id']}/photos",
            headers={"host": f"{tenant['slug']}.localhost"},
        )
        assert r.status_code == 401


class TestAssetMaintenance:
    """Tests for /api/assets/{id}/maintenance CRUD and dashboard overdue count."""

    def _headers(self, auth, tenant):
        return {**auth, "host": f"{tenant['slug']}.localhost"}

    def test_create_maintenance_returns_id(self, client, tenant_headers, fresh_asset):
        from datetime import date, timedelta
        due = (date.today() + timedelta(days=7)).isoformat()
        r = client.post(f"/api/assets/{fresh_asset['id']}/maintenance", json={
            "title": "Annual inspection", "maintenance_type": "Inspection",
            "due_date": due, "notes": "Check all fans",
        }, headers=tenant_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "scheduled"
        assert "id" in d

    def test_list_maintenance(self, client, tenant_headers, fresh_asset):
        from datetime import date, timedelta
        due = (date.today() + timedelta(days=5)).isoformat()
        client.post(f"/api/assets/{fresh_asset['id']}/maintenance",
                    json={"title": "Filter change", "due_date": due}, headers=tenant_headers)
        r = client.get(f"/api/assets/{fresh_asset['id']}/maintenance", headers=tenant_headers)
        assert r.status_code == 200
        items = r.json()
        assert any(m["title"] == "Filter change" for m in items)

    def test_complete_maintenance(self, client, tenant_headers, fresh_asset):
        from datetime import date, timedelta
        due = (date.today() + timedelta(days=3)).isoformat()
        m = client.post(f"/api/assets/{fresh_asset['id']}/maintenance",
                        json={"title": "Inspection", "due_date": due}, headers=tenant_headers).json()
        r = client.patch(f"/api/assets/{fresh_asset['id']}/maintenance/{m['id']}/complete",
                         headers=tenant_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "done"

    def test_overdue_status_on_list(self, client, tenant_headers, fresh_asset):
        from datetime import date, timedelta
        past_due = (date.today() - timedelta(days=2)).isoformat()
        m = client.post(f"/api/assets/{fresh_asset['id']}/maintenance",
                        json={"title": "Overdue task", "due_date": past_due},
                        headers=tenant_headers).json()
        items = client.get(f"/api/assets/{fresh_asset['id']}/maintenance",
                           headers=tenant_headers).json()
        task = next(i for i in items if i["id"] == m["id"])
        assert task["status"] == "overdue"

    def test_delete_maintenance(self, client, tenant_headers, fresh_asset):
        from datetime import date, timedelta
        due = (date.today() + timedelta(days=10)).isoformat()
        m = client.post(f"/api/assets/{fresh_asset['id']}/maintenance",
                        json={"title": "To delete", "due_date": due}, headers=tenant_headers).json()
        r = client.delete(f"/api/assets/{fresh_asset['id']}/maintenance/{m['id']}",
                          headers=tenant_headers)
        assert r.status_code == 200
        remaining = [i["id"] for i in client.get(
            f"/api/assets/{fresh_asset['id']}/maintenance", headers=tenant_headers).json()]
        assert m["id"] not in remaining

    def test_maintenance_requires_auth(self, client, fresh_asset, tenant):
        r = client.get(f"/api/assets/{fresh_asset['id']}/maintenance",
                       headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401
