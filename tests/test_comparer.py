from utils.comparer import detect_changes


class TestDetectChanges:
    def test_no_changes(self, snapshot):
        """Identical snapshots produce no changes."""
        assert detect_changes(snapshot, snapshot) == {}

    def test_empty_old_snapshot(self, snapshot):
        """First poll (empty old) produces no changes (prev guard)."""
        assert detect_changes({}, snapshot) == {}

    def test_epoch_change(self, usdc_asset):
        old = {"USDC": {**usdc_asset, "epoch": 62}}
        new = {"USDC": usdc_asset}  # epoch=63
        changes = detect_changes(old, new)
        assert "USDC" in changes
        assert "epoch_change" in changes["USDC"]

    def test_cap_change(self, usdc_asset):
        old = {"USDC": {**usdc_asset, "lst_cap": 2_000_000}}
        new = {"USDC": usdc_asset}  # lst_cap=3_060_000
        changes = detect_changes(old, new)
        assert "cap_change" in changes["USDC"]

    def test_tvl_change(self, usdc_asset):
        old = {"USDC": {**usdc_asset, "lst_tvl": 1_000_000}}
        new = {"USDC": usdc_asset}  # lst_tvl=2_014_600
        changes = detect_changes(old, new)
        assert "tvl_change" in changes["USDC"]

    def test_multiple_changes(self, usdc_asset):
        old = {"USDC": {**usdc_asset, "epoch": 62, "lst_cap": 1_000_000}}
        new = {"USDC": usdc_asset}
        changes = detect_changes(old, new)
        assert set(changes["USDC"]) == {"epoch_change", "cap_change"}

    def test_new_ticker_ignored(self, usdc_asset):
        """A ticker not in old is skipped (no prev → no changes)."""
        old = {}
        new = {"USDC": usdc_asset}
        assert detect_changes(old, new) == {}

    def test_removed_ticker_ignored(self, usdc_asset):
        """A ticker in old but not in new produces no entry."""
        old = {"USDC": usdc_asset}
        new = {}
        assert detect_changes(old, new) == {}

    def test_unchanged_ticker_not_in_result(self, usdc_asset, spyx_asset):
        """Only tickers with actual changes appear."""
        old = {"USDC": usdc_asset, "SPYx": {**spyx_asset, "epoch": 58}}
        new = {"USDC": usdc_asset, "SPYx": spyx_asset}
        changes = detect_changes(old, new)
        assert "USDC" not in changes
        assert "SPYx" in changes
