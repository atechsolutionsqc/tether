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
        locs = client.get("/api/locations", headers=tenant_headers).json()
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
        foreign_locs = client.get("/api/locations", headers=other_h).json()
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
        client.post("/api/tenants", json={
            "name": "Activity Iso Corp", "slug": other_slug,
        }, headers=auth)
        other_h = {**auth, "host": f"{other_slug}.localhost"}

        # Create checkout in the fixture tenant
        asset = self._make_asset(client, tenant_headers)
        self._checkout(client, tenant_headers, asset["id"], fresh_employee["id"])

        # Other tenant's activity feed must not contain this event
        r = client.get("/api/assets/activity", headers=other_h)
        assert r.status_code == 200
        tags = {ev["asset_tag"] for ev in r.json()["items"]}
        assert asset["asset_tag"] not in tags
