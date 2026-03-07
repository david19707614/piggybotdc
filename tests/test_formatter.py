import discord
import pytest

from utils.formatter import (
    _format_number,
    _merge_prev_into_context,
    build_embed,
    generate_progress_bar,
)


# ── _format_number ──────────────────────────────────────────────────

class TestFormatNumber:
    def test_integer(self):
        assert _format_number(1234.56, decimals=0) == "1235"

    def test_two_decimals(self):
        assert _format_number(1.5, decimals=2) == "1.50"

    def test_string_input(self):
        assert _format_number("42.7", decimals=1) == "42.7"

    def test_non_numeric(self):
        assert _format_number("n/a") == "n/a"

    def test_none(self):
        assert _format_number(None) == "None"


# ── generate_progress_bar ───────────────────────────────────────────

class TestProgressBar:
    def test_full(self):
        bar = generate_progress_bar(100, 100, length=10)
        assert "100%" in bar
        assert "█" * 10 in bar

    def test_empty(self):
        bar = generate_progress_bar(0, 100, length=10)
        assert "0%" in bar
        assert "░" * 10 in bar

    def test_half(self):
        bar = generate_progress_bar(50, 100, length=10)
        assert "50%" in bar

    def test_zero_max(self):
        assert generate_progress_bar(50, 0) == "N/A"

    def test_negative_max(self):
        assert generate_progress_bar(50, -10) == "N/A"

    def test_over_100_clamped(self):
        bar = generate_progress_bar(200, 100, length=10)
        assert "100%" in bar


# ── _merge_prev_into_context ────────────────────────────────────────

class TestMergePrev:
    def test_current_keys(self):
        ctx = _merge_prev_into_context({"a": 1}, {})
        assert ctx["a"] == 1

    def test_prev_prefixed(self):
        ctx = _merge_prev_into_context({}, {"epoch": 62})
        assert ctx["prev.epoch"] == 62

    def test_missing_prev_placeholders(self):
        ctx = _merge_prev_into_context({}, {})
        for key in ["prev.lst_cap", "prev.lst_tvl", "prev.epoch", "prev.epoch_start"]:
            assert key in ctx
            assert ctx[key] == ""


# ── build_embed ─────────────────────────────────────────────────────

class TestBuildEmbed:
    @pytest.fixture()
    def simple_template(self):
        return "Ticker: {{asset_ticker}} TVL: {{lst_tvl}}"

    def test_returns_embed(self, usdc_asset, simple_template):
        result = build_embed(tmpl=simple_template, asset=usdc_asset, prev={})
        assert isinstance(result, discord.Embed)

    def test_placeholder_replaced(self, usdc_asset, simple_template):
        result = build_embed(tmpl=simple_template, asset=usdc_asset, prev={})
        assert "USDC" in result.description
        assert "2014600" in result.description

    def test_unknown_placeholder_removed(self, usdc_asset):
        tmpl = "Value: {{nonexistent}}"
        result = build_embed(tmpl=tmpl, asset=usdc_asset, prev={})
        assert "{{" not in result.description

    def test_dollar_spacing(self, usdc_asset):
        tmpl = "{{lst_tvl}}$"
        result = build_embed(tmpl=tmpl, asset=usdc_asset, prev={})
        # Should separate "2014600$" into "2014600 $"
        assert "2014600 $" in result.description

    def test_capacity_bar_present(self, usdc_asset):
        tmpl = "Bar: {{capacity_bar}}"
        result = build_embed(tmpl=tmpl, asset=usdc_asset, prev={})
        assert "%" in result.description

    def test_thumbnail_from_asset_icon(self, usdc_asset):
        result = build_embed(tmpl="test", asset=usdc_asset, prev={})
        assert result.thumbnail.url == usdc_asset["asset_icon"]

    def test_footer_ticker(self, usdc_asset):
        result = build_embed(tmpl="test", asset=usdc_asset, prev={})
        assert "USDC" in result.footer.text

    def test_prev_values_accessible(self, usdc_asset):
        tmpl = "Prev epoch: {{prev.epoch}}"
        prev = {"epoch": 62}
        result = build_embed(tmpl=tmpl, asset=usdc_asset, prev=prev)
        assert "62" in result.description

    def test_tvl_diff_icon_positive(self, usdc_asset):
        """Positive tvl_diff gets a rising icon."""
        asset = {**usdc_asset, "tvl_diff": "500"}
        tmpl = "{{tvl_icon}}"
        result = build_embed(tmpl=tmpl, asset=asset, prev={})
        assert "\U0001f4c8" in result.description  # 📈

    def test_tvl_diff_icon_negative(self, usdc_asset):
        asset = {**usdc_asset, "tvl_diff": "-500"}
        tmpl = "{{tvl_icon}}"
        result = build_embed(tmpl=tmpl, asset=asset, prev={})
        assert "\U0001f4c9" in result.description  # 📉

    def test_epoch_duration_bug_fixed(self):
        """Regression: epoch_duration should be current - prev, not prev - prev."""
        asset = {
            "asset_ticker": "USDC",
            "asset_name": "Circle USD",
            "epoch_start": 2000,
            "lst_tvl": 100,
            "lst_cap": 200,
            "lst_apy": 5.0,
        }
        prev = {"epoch_start": 1000}
        tmpl = "Duration: {{epoch_duration}}"
        result = build_embed(tmpl=tmpl, asset=asset, prev=prev)
        # Should be 2000 - 1000 = 1000, NOT 0
        assert "1000" in result.description

    def test_epoch_duration_not_zero_regression(self):
        """The old bug would always produce 0 (prev - prev). Verify non-zero."""
        asset = {
            "asset_ticker": "X",
            "asset_name": "Test",
            "epoch_start": 500,
            "lst_tvl": 10,
            "lst_cap": 100,
            "lst_apy": 1.0,
        }
        prev = {"epoch_start": 300}
        tmpl = "{{epoch_duration}}"
        result = build_embed(tmpl=tmpl, asset=asset, prev=prev)
        assert result.description.strip() == "200"
