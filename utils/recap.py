"""Accumulate change events and build human-readable recap summaries."""

from __future__ import annotations

from datetime import datetime, timezone


def empty_recap_state() -> dict:
    """Return a fresh recap accumulator."""
    return {
        "period_start": datetime.now(timezone.utc).isoformat(),
        "tickers": {},
    }


def _ensure_ticker(state: dict, ticker: str) -> dict:
    """Lazily initialise a ticker entry and return it."""
    if ticker not in state["tickers"]:
        state["tickers"][ticker] = {
            "epoch_changes": 0,
            "tvl_changes": 0,
            "cap_changes": 0,
            "tvl_start": None,
            "tvl_latest": None,
            "apy_start": None,
            "apy_latest": None,
        }
    return state["tickers"][ticker]


def record_changes(state: dict, changes: dict,
                   current_snapshot: dict) -> None:
    """Update *state* in-place with newly detected *changes*.

    Parameters
    ----------
    state : recap accumulator from :func:`empty_recap_state`
    changes : output of ``detect_changes(old, new)``
    current_snapshot : the ``current`` dict used in that poll cycle
    """
    for ticker, change_list in changes.items():
        entry = _ensure_ticker(state, ticker)
        for change_type in change_list:
            if change_type == "epoch_change":
                entry["epoch_changes"] += 1
            elif change_type == "tvl_change":
                entry["tvl_changes"] += 1
            elif change_type == "cap_change":
                entry["cap_changes"] += 1

    # Track TVL / APY snapshots for every ticker present, regardless of
    # whether a change was detected this cycle.
    for ticker, asset in current_snapshot.items():
        entry = _ensure_ticker(state, ticker)
        tvl = asset.get("lst_tvl")
        apy = asset.get("lst_apy")
        if tvl is not None:
            if entry["tvl_start"] is None:
                entry["tvl_start"] = tvl
            entry["tvl_latest"] = tvl
        if apy is not None:
            if entry["apy_start"] is None:
                entry["apy_start"] = apy
            entry["apy_latest"] = apy


def _fmt_number(value: float | int | None) -> str:
    if value is None:
        return "?"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:,.2f}"


def build_recap_lines(state: dict) -> list[str]:
    """Return human-readable summary lines from the accumulated state."""
    tickers = state.get("tickers", {})
    if not tickers:
        return ["No changes recorded during this period."]

    lines: list[str] = []
    for ticker, entry in sorted(tickers.items()):
        parts: list[str] = []

        ec = entry["epoch_changes"]
        if ec:
            parts.append(f"{ec} epoch rollover{'s' if ec != 1 else ''}")

        tc = entry["tvl_changes"]
        if tc:
            tvl_s = entry.get("tvl_start")
            tvl_l = entry.get("tvl_latest")
            if tvl_s is not None and tvl_l is not None:
                diff = tvl_l - tvl_s
                sign = "+" if diff >= 0 else ""
                parts.append(
                    f"TVL {_fmt_number(tvl_s)} -> {_fmt_number(tvl_l)} "
                    f"({sign}{_fmt_number(diff)})"
                )
            else:
                parts.append(f"{tc} TVL change{'s' if tc != 1 else ''}")

        cc = entry["cap_changes"]
        if cc:
            parts.append(f"{cc} cap change{'s' if cc != 1 else ''}")

        apy_s = entry.get("apy_start")
        apy_l = entry.get("apy_latest")
        if apy_s is not None and apy_l is not None and apy_s != apy_l:
            parts.append(f"APY {apy_s:.2f}% -> {apy_l:.2f}%")

        if parts:
            lines.append(f"**{ticker}**: " + ", ".join(parts))
        else:
            lines.append(f"**{ticker}**: no changes")

    return lines
