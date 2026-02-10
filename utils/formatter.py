# utils/formatter.py
import discord
import time
import re
from typing import Dict, Any

def _format_number(value: Any, *, decimals: int = 0) -> str:
    """Formate un nombre avec le nombre de décimales demandé."""
    try:
        num = float(value)
        if decimals == 0:
            return f"{int(round(num))}"
        else:
            fmt = f"{{:.{decimals}f}}"
            return fmt.format(round(num, decimals))
    except (ValueError, TypeError):
        return str(value)


def _merge_prev_into_context(current: Dict[str, Any],
                             prev:    Dict[str, Any]) -> Dict[str, Any]:
    """Fusionne `prev` avec le préfixe « prev. », ajoute des placeholders vides."""
    merged = {}

    # Valeurs courantes (sans préfixe)
    for k, v in current.items():
        merged[k] = v

    # Valeurs précédentes avec préfixe
    for k, v in prev.items():
        merged[f"prev.{k}"] = v

    # Placeholders vides au cas où le snapshot précédent n’existe pas
    for ph in ["prev.lst_cap", "prev.lst_tvl", "prev.epoch", "prev.epoch_start"]:
        if ph not in merged:
            merged[ph] = ""

    return merged


def build_embed(*, tmpl: str, asset: Dict[str, Any], prev: Dict[str, Any]) -> discord.Embed:
    """
    Crée un embed à partir d’un template et d’un asset.
    - Calcule `last_epoch_seconds` et `epoch_duration`.
    - Arrondit `lst_tvl`, `lst_cap` (0 décimale) et `lst_apy` (2 décimales).
    - **Arrondit automatiquement tout champ se terminant par `_diff` à 2 décimales**.
    - Fusionne les valeurs précédentes (`prev.xxx`) avec le préfixe « prev. ».
    - Nettoie les placeholders non remplis et sépare le symbole `$`.
    """
    now_ts = int(time.time())

    # ---------- 1️⃣ Calculs dérivés ----------
    epoch_start = asset.get("epoch_start")
    last_epoch_seconds = now_ts - int(epoch_start) if isinstance(epoch_start, (int, float)) else 0

    epoch_duration = None
    if prev and prev.get("epoch_start"):
        epoch_duration = int(prev["epoch_start"]) - int(prev.get("epoch_start", 0))

    # ---------- 2️⃣ Préparer les données ----------
    data = dict(asset)                     # copie superficielle
    data["last_epoch_seconds"] = last_epoch_seconds
    if epoch_duration is not None:
        data["epoch_duration"] = epoch_duration

    # Arrondissements demandés
    data["lst_tvl"] = _format_number(data.get("lst_tvl"), decimals=0)
    data["lst_cap"] = _format_number(data.get("lst_cap"), decimals=0)
    data["lst_apy"] = _format_number(data.get("lst_apy"), decimals=2)

    # ---------- 3️⃣ Fusion avec le snapshot précédent ----------
    context = _merge_prev_into_context(current=data, prev=prev)

    # ---------- 4️⃣ Traitement spécial des champs *_diff ----------
    # Tous les champs qui se terminent par "_diff" (ex. tvl_diff, cap_diff)
    # seront arrondis à 2 décimales avec le signe.
    for key in list(context.keys()):
        if key.endswith("_diff"):
            # Si la valeur est déjà une chaîne formatée (ex. "+100"),
            # on tente de la convertir en float pour ré‑arrondir.
            try:
                num = float(context[key])
                # garde le signe (+/-) grâce au formatage f"{num:+.2f}"
                context[key] = f"{num:+.2f}"
            except (ValueError, TypeError):
                # si la conversion échoue, on laisse la valeur telle quelle
                pass

    # ---------- 5️⃣ Remplacement des placeholders ----------
    rendered = tmpl
    for key, val in context.items():
        placeholder = f"{{{{{key}}}}}"
        rendered = rendered.replace(placeholder, str(val))

    # Nettoyage des placeholders non remplis
    rendered = re.sub(r"\{\{.*?\}\}", "", rendered)

    # Séparer le symbole "$" collé au nombre (ex. "400$" → "400 $")
    rendered = re.sub(r"(\d+)\$", r"\1 $", rendered)

    # ---------- 6️⃣ Construction de l’embed ----------
    embed = discord.Embed(description=rendered, colour=0x2C8FFF)

    thumb_url = asset.get("asset_icon") or asset.get("lst_icon")
    if thumb_url:
        embed.set_thumbnail(url=thumb_url)

    embed.set_footer(text=f"Ticker : {asset.get('asset_ticker', 'unknown')}")
    return embed