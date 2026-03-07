"""Pure-function logic that enriches an asset dict with computed diff fields
before it is passed to the template formatter."""


def enrich_asset_for_change(change_type: str, ticker: str,
                            current: dict, prev_snapshot: dict) -> None:
    """Mutate *current[ticker]* in-place, adding diff / emoji / icon fields
    required by the template for *change_type*.

    Parameters
    ----------
    change_type : one of ``"cap_change"``, ``"tvl_change"``, ``"epoch_change"``
    ticker      : asset ticker key (e.g. ``"USDC"``)
    current     : full current snapshot dict  {ticker: asset_dict, …}
    prev_snapshot : full previous snapshot dict
    """
    asset = current[ticker]
    prev = prev_snapshot.get(ticker, {})

    if change_type == "cap_change":
        prev_cap = prev.get("lst_cap")
        cur_cap = asset.get("lst_cap")
        if prev_cap is not None and cur_cap is not None:
            diff = cur_cap - prev_cap
            asset["cap_diff"] = f"{int(round(diff)):+}"
            asset["cap_diff_raw"] = diff

    elif change_type == "tvl_change":
        prev_tvl = prev.get("lst_tvl")
        cur_tvl = asset.get("lst_tvl")
        if prev_tvl is not None and cur_tvl is not None:
            diff_tokens = cur_tvl - prev_tvl
            asset["tvl_diff"] = f"{diff_tokens:+}"
            asset["tvl_diff_raw"] = diff_tokens

            # Dollar-equivalent for emoji selection
            if ticker.upper() in ("SPYX", "JITOSOL"):
                price_usd = asset.get("current_price")
                if price_usd is None:
                    usd_amount = abs(diff_tokens)
                else:
                    usd_amount = abs(diff_tokens) * float(price_usd)
            else:
                usd_amount = abs(diff_tokens)

            if usd_amount < 1_000:
                emoji = "\U0001f990"   # shrimp
            elif usd_amount <= 10_000:
                emoji = "\U0001f42c"   # dolphin
            elif usd_amount <= 50_000:
                emoji = "\U0001f40b"   # whale
            else:
                emoji = "\U0001f419"   # octopus

            asset["tvl_emoji"] = emoji

    elif change_type == "epoch_change":
        prev_ep = prev.get("epoch")
        cur_ep = asset.get("epoch")
        if prev_ep is not None and cur_ep is not None:
            asset["epoch_change"] = f"{prev_ep} → {cur_ep}"
