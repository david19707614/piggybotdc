from utils.recap import (
    _fmt_number,
    build_recap_lines,
    empty_recap_state,
    record_changes,
)


# ── empty_recap_state ───────────────────────────────────────────────

class TestEmptyRecapState:
    def test_has_period_start(self):
        state = empty_recap_state()
        assert "period_start" in state
        assert isinstance(state["period_start"], str)

    def test_tickers_empty(self):
        state = empty_recap_state()
        assert state["tickers"] == {}


# ── record_changes ──────────────────────────────────────────────────

class TestRecordChanges:
    def _snapshot(self, tvl=2_000_000, apy=21.5):
        return {
            "USDC": {"lst_tvl": tvl, "lst_apy": apy, "lst_cap": 3_000_000},
        }

    def test_increments_epoch(self):
        state = empty_recap_state()
        record_changes(state, {"USDC": ["epoch_change"]}, self._snapshot())
        assert state["tickers"]["USDC"]["epoch_changes"] == 1

    def test_increments_tvl(self):
        state = empty_recap_state()
        record_changes(state, {"USDC": ["tvl_change"]}, self._snapshot())
        assert state["tickers"]["USDC"]["tvl_changes"] == 1

    def test_increments_cap(self):
        state = empty_recap_state()
        record_changes(state, {"USDC": ["cap_change"]}, self._snapshot())
        assert state["tickers"]["USDC"]["cap_changes"] == 1

    def test_multiple_changes_same_ticker(self):
        state = empty_recap_state()
        record_changes(state, {"USDC": ["epoch_change", "tvl_change"]},
                       self._snapshot())
        assert state["tickers"]["USDC"]["epoch_changes"] == 1
        assert state["tickers"]["USDC"]["tvl_changes"] == 1

    def test_accumulates_across_calls(self):
        state = empty_recap_state()
        record_changes(state, {"USDC": ["epoch_change"]}, self._snapshot())
        record_changes(state, {"USDC": ["epoch_change"]}, self._snapshot())
        assert state["tickers"]["USDC"]["epoch_changes"] == 2

    def test_empty_changes_no_crash(self):
        state = empty_recap_state()
        record_changes(state, {}, self._snapshot())
        # Ticker still tracked for tvl/apy snapshots
        assert "USDC" in state["tickers"]

    def test_tvl_start_set_once(self):
        state = empty_recap_state()
        record_changes(state, {}, self._snapshot(tvl=100))
        record_changes(state, {}, self._snapshot(tvl=200))
        assert state["tickers"]["USDC"]["tvl_start"] == 100
        assert state["tickers"]["USDC"]["tvl_latest"] == 200

    def test_apy_tracked(self):
        state = empty_recap_state()
        record_changes(state, {}, self._snapshot(apy=5.0))
        record_changes(state, {}, self._snapshot(apy=6.0))
        assert state["tickers"]["USDC"]["apy_start"] == 5.0
        assert state["tickers"]["USDC"]["apy_latest"] == 6.0

    def test_multiple_tickers(self):
        state = empty_recap_state()
        snap = {
            "USDC": {"lst_tvl": 100, "lst_apy": 5.0},
            "SPYx": {"lst_tvl": 200, "lst_apy": 3.0},
        }
        record_changes(state, {"USDC": ["epoch_change"]}, snap)
        assert state["tickers"]["USDC"]["epoch_changes"] == 1
        assert state["tickers"]["SPYx"]["epoch_changes"] == 0


# ── _fmt_number ─────────────────────────────────────────────────────

class TestFmtNumber:
    def test_millions(self):
        assert _fmt_number(2_500_000) == "2.50M"

    def test_thousands(self):
        assert _fmt_number(5_400) == "5.4k"

    def test_small(self):
        assert _fmt_number(42.5) == "42.50"

    def test_none(self):
        assert _fmt_number(None) == "?"

    def test_negative_millions(self):
        assert _fmt_number(-1_200_000) == "-1.20M"


# ── build_recap_lines ──────────────────────────────────────────────

class TestBuildRecapLines:
    def test_no_tickers(self):
        state = empty_recap_state()
        lines = build_recap_lines(state)
        assert len(lines) == 1
        assert "No changes" in lines[0]

    def test_epoch_reported(self):
        state = empty_recap_state()
        state["tickers"]["USDC"] = {
            "epoch_changes": 3, "tvl_changes": 0, "cap_changes": 0,
            "tvl_start": None, "tvl_latest": None,
            "apy_start": None, "apy_latest": None,
        }
        lines = build_recap_lines(state)
        assert any("3 epoch rollovers" in l for l in lines)

    def test_single_epoch_no_plural(self):
        state = empty_recap_state()
        state["tickers"]["USDC"] = {
            "epoch_changes": 1, "tvl_changes": 0, "cap_changes": 0,
            "tvl_start": None, "tvl_latest": None,
            "apy_start": None, "apy_latest": None,
        }
        lines = build_recap_lines(state)
        assert any("1 epoch rollover" in l and "rollovers" not in l
                    for l in lines)

    def test_tvl_with_diff(self):
        state = empty_recap_state()
        state["tickers"]["USDC"] = {
            "epoch_changes": 0, "tvl_changes": 2, "cap_changes": 0,
            "tvl_start": 1_000_000, "tvl_latest": 1_100_000,
            "apy_start": None, "apy_latest": None,
        }
        lines = build_recap_lines(state)
        joined = " ".join(lines)
        assert "TVL" in joined
        assert "1.00M" in joined
        assert "1.10M" in joined

    def test_apy_change_shown(self):
        state = empty_recap_state()
        state["tickers"]["USDC"] = {
            "epoch_changes": 0, "tvl_changes": 0, "cap_changes": 0,
            "tvl_start": None, "tvl_latest": None,
            "apy_start": 5.0, "apy_latest": 6.5,
        }
        lines = build_recap_lines(state)
        joined = " ".join(lines)
        assert "APY" in joined
        assert "5.00%" in joined
        assert "6.50%" in joined

    def test_no_changes_for_ticker(self):
        state = empty_recap_state()
        state["tickers"]["USDC"] = {
            "epoch_changes": 0, "tvl_changes": 0, "cap_changes": 0,
            "tvl_start": None, "tvl_latest": None,
            "apy_start": 5.0, "apy_latest": 5.0,  # same APY
        }
        lines = build_recap_lines(state)
        assert any("no changes" in l for l in lines)
