import copy

from utils.enricher import enrich_asset_for_change


class TestCapChange:
    def test_cap_diff_positive(self, usdc_asset):
        prev_snapshot = {"USDC": {**usdc_asset, "lst_cap": 2_000_000}}
        current = {"USDC": copy.deepcopy(usdc_asset)}  # lst_cap=3_060_000
        enrich_asset_for_change("cap_change", "USDC", current, prev_snapshot)
        assert current["USDC"]["cap_diff"] == "+1060000"
        assert current["USDC"]["cap_diff_raw"] == 1_060_000

    def test_cap_diff_negative(self, usdc_asset):
        prev_snapshot = {"USDC": {**usdc_asset, "lst_cap": 4_000_000}}
        current = {"USDC": copy.deepcopy(usdc_asset)}
        enrich_asset_for_change("cap_change", "USDC", current, prev_snapshot)
        assert current["USDC"]["cap_diff"].startswith("-")

    def test_cap_diff_missing_prev(self, usdc_asset):
        """No prev ticker → no cap_diff injected."""
        current = {"USDC": copy.deepcopy(usdc_asset)}
        enrich_asset_for_change("cap_change", "USDC", current, {})
        assert "cap_diff" not in current["USDC"]


class TestTvlChange:
    def test_tvl_diff_and_emoji_usdc(self, usdc_asset):
        prev_snapshot = {"USDC": {**usdc_asset, "lst_tvl": 2_014_100}}
        current = {"USDC": copy.deepcopy(usdc_asset)}  # lst_tvl=2_014_600
        enrich_asset_for_change("tvl_change", "USDC", current, prev_snapshot)
        assert current["USDC"]["tvl_diff"] == "+500"
        assert current["USDC"]["tvl_diff_raw"] == 500
        # 500 USDC < 1000 → shrimp
        assert current["USDC"]["tvl_emoji"] == "\U0001f990"

    def test_tvl_emoji_dolphin(self, usdc_asset):
        prev_snapshot = {"USDC": {**usdc_asset, "lst_tvl": 2_009_600}}
        current = {"USDC": copy.deepcopy(usdc_asset)}  # diff = 5000
        enrich_asset_for_change("tvl_change", "USDC", current, prev_snapshot)
        assert current["USDC"]["tvl_emoji"] == "\U0001f42c"  # dolphin

    def test_tvl_emoji_whale(self, usdc_asset):
        prev_snapshot = {"USDC": {**usdc_asset, "lst_tvl": 1_994_600}}
        current = {"USDC": copy.deepcopy(usdc_asset)}  # diff = 20000
        enrich_asset_for_change("tvl_change", "USDC", current, prev_snapshot)
        assert current["USDC"]["tvl_emoji"] == "\U0001f40b"  # whale

    def test_tvl_emoji_octopus(self, usdc_asset):
        prev_snapshot = {"USDC": {**usdc_asset, "lst_tvl": 1_914_600}}
        current = {"USDC": copy.deepcopy(usdc_asset)}  # diff = 100_000
        enrich_asset_for_change("tvl_change", "USDC", current, prev_snapshot)
        assert current["USDC"]["tvl_emoji"] == "\U0001f419"  # octopus

    def test_spyx_uses_price_for_emoji(self, spyx_asset):
        """SPYx multiplies diff by current_price for emoji threshold."""
        # diff = 1 token, price ~690 → 690 USD → shrimp
        prev_snapshot = {"SPYx": {**spyx_asset, "lst_tvl": 270.003}}
        current = {"SPYx": copy.deepcopy(spyx_asset)}  # lst_tvl=271.003
        enrich_asset_for_change("tvl_change", "SPYx", current, prev_snapshot)
        assert current["SPYx"]["tvl_emoji"] == "\U0001f990"  # shrimp

    def test_spyx_whale_with_price(self, spyx_asset):
        """50 SPYx * $690 ≈ $34.5k → whale."""
        prev_snapshot = {"SPYx": {**spyx_asset, "lst_tvl": 221.003}}
        current = {"SPYx": copy.deepcopy(spyx_asset)}  # diff = 50
        enrich_asset_for_change("tvl_change", "SPYx", current, prev_snapshot)
        assert current["SPYx"]["tvl_emoji"] == "\U0001f40b"  # whale

    def test_tvl_diff_missing_prev(self, usdc_asset):
        current = {"USDC": copy.deepcopy(usdc_asset)}
        enrich_asset_for_change("tvl_change", "USDC", current, {})
        assert "tvl_diff" not in current["USDC"]


class TestEpochChange:
    def test_epoch_arrow(self, usdc_asset):
        prev_snapshot = {"USDC": {**usdc_asset, "epoch": 62}}
        current = {"USDC": copy.deepcopy(usdc_asset)}  # epoch=63
        enrich_asset_for_change("epoch_change", "USDC", current, prev_snapshot)
        assert current["USDC"]["epoch_change"] == "62 → 63"

    def test_epoch_missing_prev(self, usdc_asset):
        current = {"USDC": copy.deepcopy(usdc_asset)}
        enrich_asset_for_change("epoch_change", "USDC", current, {})
        assert "epoch_change" not in current["USDC"]


class TestUnknownChangeType:
    def test_unknown_type_is_noop(self, usdc_asset):
        """An unrecognised change_type should not raise or mutate."""
        current = {"USDC": copy.deepcopy(usdc_asset)}
        original = copy.deepcopy(current)
        enrich_asset_for_change("unknown_change", "USDC", current, {})
        assert current == original
