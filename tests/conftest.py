import pytest


def _make_asset(*, ticker="USDC", epoch=63, lst_cap=3_060_000, lst_tvl=2_014_600,
                epoch_start=1_770_389_021, lst_apy=21.5, current_price=1.0,
                asset_name="Circle USD", **extra):
    """Return a minimal asset dict matching the PiggyBank API shape."""
    d = {
        "asset_ticker": ticker,
        "asset_name": asset_name,
        "epoch": epoch,
        "lst_cap": lst_cap,
        "lst_tvl": lst_tvl,
        "epoch_start": epoch_start,
        "lst_apy": lst_apy,
        "current_price": current_price,
        "asset_icon": f"https://example.com/{ticker}.svg",
    }
    d.update(extra)
    return d


@pytest.fixture()
def usdc_asset():
    return _make_asset()


@pytest.fixture()
def spyx_asset():
    return _make_asset(
        ticker="SPYx", asset_name="S&P 500", epoch=59,
        lst_cap=400, lst_tvl=271.003, epoch_start=1_770_389_323,
        lst_apy=5.64, current_price=690.62,
    )


@pytest.fixture()
def jitosol_asset():
    return _make_asset(
        ticker="JITOSOL", asset_name="Jito SOL", epoch=30,
        lst_cap=5000, lst_tvl=2521.156, epoch_start=1_770_389_211,
        lst_apy=4.94, current_price=99.80,
    )


@pytest.fixture()
def snapshot(usdc_asset, spyx_asset, jitosol_asset):
    """A full three-asset snapshot dict."""
    return {
        "USDC": usdc_asset,
        "SPYx": spyx_asset,
        "JITOSOL": jitosol_asset,
    }
