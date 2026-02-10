def detect_changes(old: dict, new: dict) -> dict:
    """
    Compare two snapshots (both dict[ticker] -> asset dict).
    Returns a dict[ticker] -> list of change identifiers:
    possible identifiers: "epoch_change", "cap_change", "tvl_change"
    """
    changes = {}
    for ticker, cur in new.items():
        prev = old.get(ticker, {})
        ticker_changes = []

        if prev and cur.get("epoch") != prev.get("epoch"):
            ticker_changes.append("epoch_change")

        if prev and cur.get("lst_cap") != prev.get("lst_cap"):
            ticker_changes.append("cap_change")

        if prev and cur.get("lst_tvl") != prev.get("lst_tvl"):
            ticker_changes.append("tvl_change")

        if ticker_changes:
            changes[ticker] = ticker_changes
    return changes