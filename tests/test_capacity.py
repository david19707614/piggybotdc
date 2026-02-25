import copy

from utils.capacity import (
    FILL_THRESHOLD,
    check_deposit_alerts,
    compute_fill_ratio,
    enrich_capacity_fields,
)


# ── compute_fill_ratio ──────────────────────────────────────────────

class TestComputeFillRatio:
    def test_normal(self):
        assert compute_fill_ratio({"lst_tvl": 50, "lst_cap": 100}) == 0.5

    def test_full(self):
        assert compute_fill_ratio({"lst_tvl": 100, "lst_cap": 100}) == 1.0

    def test_over_100(self):
        ratio = compute_fill_ratio({"lst_tvl": 120, "lst_cap": 100})
        assert ratio == 1.2

    def test_zero_cap(self):
        assert compute_fill_ratio({"lst_tvl": 50, "lst_cap": 0}) is None

    def test_negative_cap(self):
        assert compute_fill_ratio({"lst_tvl": 50, "lst_cap": -10}) is None

    def test_missing_tvl(self):
        assert compute_fill_ratio({"lst_cap": 100}) is None

    def test_missing_cap(self):
        assert compute_fill_ratio({"lst_tvl": 50}) is None

    def test_empty_dict(self):
        assert compute_fill_ratio({}) is None


# ── check_deposit_alerts ────────────────────────────────────────────

class TestCheckDepositAlerts:
    def _make(self, tvl, cap=100):
        return {"lst_tvl": tvl, "lst_cap": cap, "asset_ticker": "X",
                "asset_name": "Test"}

    def test_crosses_above_threshold(self):
        prev = {"X": self._make(90)}     # 90% < 95%
        cur = {"X": self._make(96)}      # 96% >= 95%
        alerts = check_deposit_alerts("X", cur, prev)
        assert alerts == ["vault_nearly_full"]

    def test_crosses_below_threshold(self):
        prev = {"X": self._make(96)}     # 96% >= 95%
        cur = {"X": self._make(90)}      # 90% < 95%
        alerts = check_deposit_alerts("X", cur, prev)
        assert alerts == ["vault_space_opened"]

    def test_stays_above(self):
        prev = {"X": self._make(96)}
        cur = {"X": self._make(98)}
        alerts = check_deposit_alerts("X", cur, prev)
        assert alerts == []

    def test_stays_below(self):
        prev = {"X": self._make(80)}
        cur = {"X": self._make(85)}
        alerts = check_deposit_alerts("X", cur, prev)
        assert alerts == []

    def test_exactly_at_threshold(self):
        prev = {"X": self._make(94)}
        cur = {"X": self._make(95)}      # exactly 95% → >= threshold
        alerts = check_deposit_alerts("X", cur, prev)
        assert alerts == ["vault_nearly_full"]

    def test_no_prev_data(self):
        cur = {"X": self._make(96)}
        alerts = check_deposit_alerts("X", cur, {})
        assert alerts == []

    def test_ticker_missing_from_current(self):
        prev = {"X": self._make(90)}
        alerts = check_deposit_alerts("X", {}, prev)
        assert alerts == []

    def test_custom_threshold(self):
        prev = {"X": self._make(80)}
        cur = {"X": self._make(91)}
        alerts = check_deposit_alerts("X", cur, prev, threshold=0.90)
        assert alerts == ["vault_nearly_full"]

    def test_missing_cap_in_current(self):
        prev = {"X": self._make(90)}
        cur = {"X": {"lst_tvl": 96}}     # no lst_cap
        alerts = check_deposit_alerts("X", cur, prev)
        assert alerts == []


# ── enrich_capacity_fields ──────────────────────────────────────────

class TestEnrichCapacityFields:
    def test_adds_fill_pct_and_remaining(self):
        asset = {"lst_tvl": 80, "lst_cap": 100}
        enrich_capacity_fields(asset)
        assert asset["fill_pct"] == "80.0"
        assert asset["remaining"] == "20"

    def test_full_vault(self):
        asset = {"lst_tvl": 100, "lst_cap": 100}
        enrich_capacity_fields(asset)
        assert asset["fill_pct"] == "100.0"
        assert asset["remaining"] == "0"

    def test_missing_data(self):
        asset = {"lst_tvl": 50}
        enrich_capacity_fields(asset)
        assert asset["fill_pct"] == "N/A"
        assert asset["remaining"] == "N/A"
