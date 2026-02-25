from utils.vault_detector import detect_new_vaults, find_vault_assets


# ── find_vault_assets ───────────────────────────────────────────────

class TestFindVaultAssets:
    def test_identifies_assets_with_lst_cap(self):
        assets = {
            "USDC": {"lst_cap": 3_000_000, "lst_tvl": 2_000_000},
            "SPYx": {"lst_cap": 400, "lst_tvl": 271},
            "NVDAx": {"current_price": 185.0},  # no vault
        }
        result = find_vault_assets(assets)
        assert result == {"USDC", "SPYx"}

    def test_skips_none_lst_cap(self):
        assets = {
            "USDC": {"lst_cap": 1000},
            "FAKE": {"lst_cap": None},
        }
        result = find_vault_assets(assets)
        assert result == {"USDC"}

    def test_zero_cap_still_counts(self):
        assets = {"X": {"lst_cap": 0}}
        result = find_vault_assets(assets)
        assert result == {"X"}

    def test_empty_assets(self):
        assert find_vault_assets({}) == set()

    def test_no_vaults(self):
        assets = {
            "A": {"current_price": 1.0},
            "B": {"current_price": 2.0},
        }
        assert find_vault_assets(assets) == set()


# ── detect_new_vaults ──────────────────────────────────────────────

class TestDetectNewVaults:
    def test_new_vault_detected(self):
        assets = {
            "USDC": {"lst_cap": 1000},
            "NVDAx": {"lst_cap": 500},  # new!
        }
        known = {"USDC"}
        result = detect_new_vaults(assets, known)
        assert result == ["NVDAx"]

    def test_no_new_vaults(self):
        assets = {
            "USDC": {"lst_cap": 1000},
            "SPYx": {"lst_cap": 400},
        }
        known = {"USDC", "SPYx"}
        assert detect_new_vaults(assets, known) == []

    def test_all_known(self):
        assets = {
            "USDC": {"lst_cap": 1000},
        }
        known = {"USDC", "SPYx", "JITOSOL"}
        assert detect_new_vaults(assets, known) == []

    def test_empty_known_first_run(self):
        """First run: all vaults are 'new'."""
        assets = {
            "USDC": {"lst_cap": 1000},
            "SPYx": {"lst_cap": 400},
            "NVDAx": {"current_price": 100},  # no vault
        }
        result = detect_new_vaults(assets, set())
        assert result == ["SPYx", "USDC"]  # sorted

    def test_multiple_new_vaults(self):
        assets = {
            "USDC": {"lst_cap": 1000},
            "NVDAx": {"lst_cap": 500},
            "TSLAx": {"lst_cap": 300},
        }
        known = {"USDC"}
        result = detect_new_vaults(assets, known)
        assert result == ["NVDAx", "TSLAx"]  # sorted

    def test_asset_without_vault_not_detected(self):
        assets = {
            "USDC": {"lst_cap": 1000},
            "NVDAx": {"current_price": 100},  # still no vault
        }
        known = {"USDC"}
        assert detect_new_vaults(assets, known) == []

    def test_returns_sorted(self):
        assets = {
            "ZZZ": {"lst_cap": 1},
            "AAA": {"lst_cap": 2},
            "MMM": {"lst_cap": 3},
        }
        result = detect_new_vaults(assets, set())
        assert result == ["AAA", "MMM", "ZZZ"]
