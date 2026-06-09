"""
test_depreciation.py — Straight-line depreciation tracking tests.

Covers:
  - calculate_depreciation returns None when required fields are missing
  - Correct book value for a known scenario
  - current_value never goes below salvage_value
  - fully_depreciated flag is True when end_of_life is in the past
  - GET /api/assets/{id} includes depreciation object when fields are set
  - GET /api/assets/{id} depreciation is None when useful_life_years not set
  - GET /api/reports/depreciation returns items and summary
  - fully_depreciated filter works correctly
  - Assets without purchase_cost excluded from depreciation report
"""
import time
from datetime import date, timedelta


# ── Unit tests for the helper function ────────────────────────────────────────

class TestCalculateDepreciation:
    """Tests against the calculate_depreciation() function directly."""

    @staticmethod
    def _mock_asset(**kwargs):
        """Return a simple namespace object mimicking an Asset ORM row."""
        from types import SimpleNamespace
        defaults = dict(
            purchase_cost=None,
            purchase_date=None,
            useful_life_years=None,
            salvage_value=None,
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_returns_none_when_purchase_cost_missing(self):
        from routers.assets import calculate_depreciation
        a = self._mock_asset(
            purchase_date=date(2020, 1, 1),
            useful_life_years=5,
        )
        assert calculate_depreciation(a) is None

    def test_returns_none_when_purchase_date_missing(self):
        from routers.assets import calculate_depreciation
        a = self._mock_asset(purchase_cost=1000.0, useful_life_years=5)
        assert calculate_depreciation(a) is None

    def test_returns_none_when_useful_life_years_missing(self):
        from routers.assets import calculate_depreciation
        a = self._mock_asset(
            purchase_cost=1000.0,
            purchase_date=date(2020, 1, 1),
        )
        assert calculate_depreciation(a) is None

    def test_correct_current_value_known_scenario(self):
        """$1000 cost, 0 salvage, 5-year life, purchased exactly 2.5 years ago ≈ $500."""
        from routers.assets import calculate_depreciation
        purchase = date.today() - timedelta(days=round(365.25 * 2.5))
        a = self._mock_asset(
            purchase_cost=1000.0,
            purchase_date=purchase,
            useful_life_years=5,
            salvage_value=0.0,
        )
        dep = calculate_depreciation(a)
        assert dep is not None
        # Annual = 200; 2.5 years = 500 depreciated; book value ≈ 500
        assert 480 <= dep["current_value"] <= 520, f"Expected ~500, got {dep['current_value']}"
        assert dep["annual_depreciation"] == 200.0
        assert 45 <= dep["depreciation_pct"] <= 55

    def test_current_value_never_below_salvage(self):
        from routers.assets import calculate_depreciation
        # Asset purchased 20 years ago with 3-year life — fully depreciated
        a = self._mock_asset(
            purchase_cost=1000.0,
            purchase_date=date.today() - timedelta(days=365 * 20),
            useful_life_years=3,
            salvage_value=150.0,
        )
        dep = calculate_depreciation(a)
        assert dep is not None
        assert dep["current_value"] >= 150.0
        assert dep["current_value"] == 150.0   # salvage floor

    def test_fully_depreciated_when_past_end_of_life(self):
        from routers.assets import calculate_depreciation
        old_purchase = date.today() - timedelta(days=365 * 10)
        a = self._mock_asset(
            purchase_cost=1000.0,
            purchase_date=old_purchase,
            useful_life_years=5,
        )
        dep = calculate_depreciation(a)
        assert dep is not None
        assert dep["fully_depreciated"] is True
        assert dep["days_remaining"] < 0

    def test_not_fully_depreciated_for_new_asset(self):
        from routers.assets import calculate_depreciation
        a = self._mock_asset(
            purchase_cost=1000.0,
            purchase_date=date.today() - timedelta(days=30),
            useful_life_years=5,
        )
        dep = calculate_depreciation(a)
        assert dep is not None
        assert dep["fully_depreciated"] is False
        assert dep["days_remaining"] > 0

    def test_returns_none_when_depreciable_amount_is_zero(self):
        """salvage_value == purchase_cost means nothing to depreciate."""
        from routers.assets import calculate_depreciation
        a = self._mock_asset(
            purchase_cost=500.0,
            purchase_date=date(2020, 1, 1),
            useful_life_years=5,
            salvage_value=500.0,
        )
        assert calculate_depreciation(a) is None


# ── API integration tests ──────────────────────────────────────────────────────

def _tag():
    return f"DEP-{int(time.time() * 1000) % 999999:06d}"


def _create_asset_with_depreciation(client, tenant_headers, **overrides):
    payload = {
        "asset_tag":          _tag(),
        "name":               "Depreciable Laptop",
        "status":             "available",
        "purchase_cost":      1000.0,
        "purchase_date":      (date.today() - timedelta(days=round(365.25 * 2))).isoformat(),
        "useful_life_years":  5,
        "salvage_value":      100.0,
    }
    payload.update(overrides)
    r = client.post("/api/assets", json=payload, headers=tenant_headers)
    assert r.status_code == 200, f"Asset creation failed: {r.text}"
    return r.json()


class TestAssetDepreciationAPI:
    def test_single_asset_includes_depreciation_object(self, client, tenant_headers):
        a = _create_asset_with_depreciation(client, tenant_headers)
        r = client.get(f"/api/assets/{a['id']}", headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert "depreciation" in data
        dep = data["depreciation"]
        assert dep is not None
        for key in ("current_value", "annual_depreciation", "depreciation_pct",
                    "end_of_life_date", "fully_depreciated", "total_depreciation"):
            assert key in dep, f"Missing key: {key}"

    def test_depreciation_is_none_when_useful_life_not_set(self, client, tenant_headers):
        r = client.post("/api/assets", json={
            "asset_tag":     _tag(),
            "name":          "No Depreciation",
            "status":        "available",
            "purchase_cost": 500.0,
            "purchase_date": "2022-01-01",
        }, headers=tenant_headers)
        assert r.status_code == 200
        asset_id = r.json()["id"]

        r2 = client.get(f"/api/assets/{asset_id}", headers=tenant_headers)
        assert r2.status_code == 200
        assert r2.json()["depreciation"] is None

    def test_depreciation_current_value_is_plausible(self, client, tenant_headers):
        """$1000 purchase 2 years ago, 5-year life, $0 salvage → ~$600 book value."""
        a = _create_asset_with_depreciation(
            client, tenant_headers,
            purchase_cost=1000.0,
            purchase_date=(date.today() - timedelta(days=round(365.25 * 2))).isoformat(),
            useful_life_years=5,
            salvage_value=0.0,
        )
        r = client.get(f"/api/assets/{a['id']}", headers=tenant_headers)
        dep = r.json()["depreciation"]
        # ~$600 book value (2/5 depreciated from $1000)
        assert 550 <= dep["current_value"] <= 650, f"Unexpected book value: {dep['current_value']}"

    def test_depreciation_not_included_in_list_endpoint(self, client, tenant_headers):
        """List endpoint omits depreciation to avoid N+1 cost."""
        _create_asset_with_depreciation(client, tenant_headers)
        r = client.get("/api/assets", headers=tenant_headers)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert "depreciation" not in item


class TestDepreciationReport:
    def test_report_returns_items_and_summary(self, client, tenant_headers):
        _create_asset_with_depreciation(client, tenant_headers)
        r = client.get("/api/reports/depreciation", headers=tenant_headers)
        assert r.status_code == 200
        data = r.json()
        assert "items"   in data
        assert "summary" in data
        s = data["summary"]
        for key in ("total_purchase_value", "total_current_value",
                    "total_depreciated", "fully_depreciated_count", "tracked_asset_count"):
            assert key in s, f"Missing summary key: {key}"

    def test_report_tracked_count_increases(self, client, tenant_headers):
        r1 = client.get("/api/reports/depreciation", headers=tenant_headers)
        before = r1.json()["summary"]["tracked_asset_count"]

        _create_asset_with_depreciation(client, tenant_headers)

        r2 = client.get("/api/reports/depreciation", headers=tenant_headers)
        after = r2.json()["summary"]["tracked_asset_count"]
        assert after == before + 1

    def test_fully_depreciated_filter_true(self, client, tenant_headers):
        # Old asset — fully depreciated
        client.post("/api/assets", json={
            "asset_tag":         _tag(),
            "name":              "Old Machine",
            "status":            "retired",
            "purchase_cost":     500.0,
            "purchase_date":     (date.today() - timedelta(days=365 * 10)).isoformat(),
            "useful_life_years": 3,
        }, headers=tenant_headers)

        r = client.get("/api/reports/depreciation?fully_depreciated=true",
                       headers=tenant_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(i["fully_depreciated"] for i in items)

    def test_fully_depreciated_filter_false(self, client, tenant_headers):
        r = client.get("/api/reports/depreciation?fully_depreciated=false",
                       headers=tenant_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(not i["fully_depreciated"] for i in items)

    def test_assets_without_purchase_cost_excluded(self, client, tenant_headers):
        # Asset with no purchase_cost — must not appear in report
        r = client.post("/api/assets", json={
            "asset_tag":         _tag(),
            "name":              "No Cost Asset",
            "status":            "available",
            "useful_life_years": 5,
        }, headers=tenant_headers)
        assert r.status_code == 200
        excluded_tag = r.json()["asset_tag"]

        report = client.get("/api/reports/depreciation", headers=tenant_headers)
        tags = {i["asset_tag"] for i in report.json()["items"]}
        assert excluded_tag not in tags

    def test_report_sorted_by_depreciation_pct_descending(self, client, tenant_headers):
        # Create two assets: one near end-of-life, one brand-new
        client.post("/api/assets", json={
            "asset_tag":         _tag(),
            "name":              "Old Asset Sort",
            "status":            "available",
            "purchase_cost":     1000.0,
            "purchase_date":     (date.today() - timedelta(days=365 * 4)).isoformat(),
            "useful_life_years": 5,
        }, headers=tenant_headers)
        client.post("/api/assets", json={
            "asset_tag":         _tag(),
            "name":              "New Asset Sort",
            "status":            "available",
            "purchase_cost":     1000.0,
            "purchase_date":     (date.today() - timedelta(days=30)).isoformat(),
            "useful_life_years": 5,
        }, headers=tenant_headers)

        r = client.get("/api/reports/depreciation", headers=tenant_headers)
        items = r.json()["items"]
        pcts = [i["depreciation_pct"] for i in items]
        assert pcts == sorted(pcts, reverse=True)

    def test_report_requires_authentication(self, client, tenant):
        r = client.get("/api/reports/depreciation",
                       headers={"host": f"{tenant['slug']}.localhost"})
        assert r.status_code == 401

    def test_depreciation_csv_export(self, client, tenant_headers):
        _create_asset_with_depreciation(client, tenant_headers)
        r = client.get("/api/reports/depreciation/export", headers=tenant_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        lines = r.text.strip().splitlines()
        assert lines[0].startswith("asset_tag")
        assert len(lines) >= 2
