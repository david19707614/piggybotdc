"""Detect when PiggyBank launches a new vault for an existing asset."""

from __future__ import annotations


def find_vault_assets(assets: dict) -> set[str]:
    """Return the set of tickers that have an active vault.

    An asset is considered to have a vault when it has a ``lst_cap`` field
    with a non-None value.
    """
    return {
        ticker
        for ticker, asset in assets.items()
        if asset.get("lst_cap") is not None
    }


def detect_new_vaults(all_assets: dict,
                      known_vault_tickers: set[str]) -> list[str]:
    """Return tickers that now have vaults but are not in *known_vault_tickers*.

    Returns a sorted list for deterministic ordering.
    """
    current_vaults = find_vault_assets(all_assets)
    new = current_vaults - known_vault_tickers
    return sorted(new)
