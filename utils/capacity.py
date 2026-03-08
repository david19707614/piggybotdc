"""Deposit opportunity alerts — detect when vaults cross fill thresholds."""

FILL_THRESHOLD = 0.95  # 95%


def compute_fill_ratio(asset: dict) -> float | None:
    """Return lst_tvl / lst_cap, or None if data is missing or cap is zero."""
    tvl = asset.get("lst_tvl")
    cap = asset.get("lst_cap")
    if tvl is None or cap is None or cap <= 0:
        return None
    return tvl / cap


def check_deposit_alerts(ticker: str, current: dict, prev_snapshot: dict,
                         threshold: float = FILL_THRESHOLD) -> list[str]:
    """Return a list of alert type strings.

    Possible values:
    - ``"vault_nearly_full"`` — fill ratio just crossed *above* threshold
    - ``"vault_space_opened"`` — fill ratio just crossed *below* threshold
    """
    cur_asset = current.get(ticker)
    if cur_asset is None:
        return []

    cur_ratio = compute_fill_ratio(cur_asset)
    if cur_ratio is None:
        return []

    prev_asset = prev_snapshot.get(ticker)
    if prev_asset is None:
        # First poll — no previous data to compare against
        return []

    prev_ratio = compute_fill_ratio(prev_asset)
    if prev_ratio is None:
        return []

    alerts: list[str] = []

    if cur_ratio >= threshold and prev_ratio < threshold:
        alerts.append("vault_nearly_full")

    if cur_ratio < threshold and prev_ratio >= threshold:
        alerts.append("vault_space_opened")

    return alerts


def enrich_capacity_fields(asset: dict) -> None:
    """Add ``fill_pct`` and ``remaining`` fields to *asset* in-place."""
    ratio = compute_fill_ratio(asset)
    if ratio is not None:
        asset["fill_pct"] = f"{ratio * 100:.1f}"
        cap = asset["lst_cap"]
        tvl = asset["lst_tvl"]
        asset["remaining"] = f"{cap - tvl:,.0f}"
    else:
        asset["fill_pct"] = "N/A"
        asset["remaining"] = "N/A"
