# utils/formatter.py
import discord
import time
import re
import os
import math
from typing import Dict, Any

# -------------------------------------------------
# Caractères de la barre de progression
# -------------------------------------------------
_FILLED_CHAR = "█"   # bloc plein
_EMPTY_CHAR  = "░"   # bloc vide (utilisé pour les parties non remplies)


# -------------------------------------------------
# Helper – formatage numérique
# -------------------------------------------------
def _format_number(value: Any, *, decimals: int = 0) -> str:
    """Formate un nombre avec le nombre de décimales demandé."""
    try:
        num = float(value)
        if decimals == 0:
            return f"{int(round(num))}"
        fmt = f"{{:.{decimals}f}}"
        return fmt.format(round(num, decimals))
    except (ValueError, TypeError):
        return str(value)


# -------------------------------------------------
# Fonction de génération de la barre de progression
# -------------------------------------------------
def generate_progress_bar(
    current: float,
    maximum: float,
    *,
    length: int = 20,
    suffix: str = "",
    decimals: int = 2,
) -> str:
    """
    Retourne une chaîne prête à être insérée dans le template :

        Filled: <current> / <maximum> <suffix> `[bar]` <percent>% 
        available: <remaining>
    """
    if maximum <= 0:
        return "N/A"

    ratio = max(0.0, min(1.0, current / maximum))
    percent = ratio * 100

    filled_len = int(round(ratio * length))
    empty_len = length - filled_len
    bar = f"`{'█' * filled_len}{'░' * empty_len}`"

    # Helpers de formatage
    def _fmt_int(num: Any) -> str:
        try:
            return f"{int(round(float(num))):,}"
        except Exception:
            return str(num)

    def _fmt_dec(num: Any, dec: int = 0) -> str:
        try:
            if dec == 0:
                return f"{int(round(float(num))):,}"
            return f"{float(num):,.{dec}f}"
        except Exception:
            return str(num)

    cur_str = _fmt_int(current)
    max_str = _fmt_int(maximum)

    remaining = max(0.0, maximum - current)
    remaining_str = _fmt_dec(remaining, decimals)

    return (
        f"Filled: {cur_str} / {max_str}\n"
        f"{bar} {percent:.{decimals}f}%\n"
        f"Available: {remaining_str}"
    )


# -------------------------------------------------
# Fusion du snapshot précédent (inchangé)
# -------------------------------------------------
def _merge_prev_into_context(current: Dict[str, Any],
                             prev:    Dict[str, Any]) -> Dict[str, Any]:
    """Fusionne `prev` avec le préfixe « prev. », ajoute des placeholders vides."""
    merged = {}

    for k, v in current.items():
        merged[k] = v
    for k, v in prev.items():
        merged[f"prev.{k}"] = v

    for ph in ["prev.lst_cap", "prev.lst_tvl", "prev.epoch", "prev.epoch_start"]:
        if ph not in merged:
            merged[ph] = ""

    return merged


# -------------------------------------------------
# CUSTOM ASSET NAME – mapping ticker → affichage décoré
# -------------------------------------------------
_ASSET_NAME_MAP = {
    "USDC":    "🟦 **Circle USD**",
    "SPYX":    "🟥 **S&P 500**",
    "JITOSOL": "🟩 **Jito SOL**",
}


def _pretty_asset_name(ticker: str) -> str:
    """Retourne le nom décoré à placer dans le template."""
    return _ASSET_NAME_MAP.get(ticker.upper(), ticker)


# -------------------------------------------------
# Fonction principale – build_embed
# -------------------------------------------------
def build_embed(*, tmpl: str, asset: Dict[str, Any], prev: Dict[str, Any]) -> discord.Embed:
    """
    Crée un embed à partir d’un template et d’un asset.
    - Calcule `last_epoch_seconds` et `epoch_duration`.
    - Formate `lst_tvl`, `lst_cap` (0 décimale) et `lst_apy` (2 décimales).
    - Formate toutes les valeurs `_diff` (et `cap_diff`) avec séparateurs de milliers.
    - **tvl_change** : le texte « Capacity changed » devient dynamique :
        * 📈 Deposit 📈  si le TVL augmente
        * 📉 Withdrawal 📉 si le TVL diminue
    - Le reste (progress bar, icônes, etc.) reste inchangé.
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

    # Arrondissements de base (sans séparateurs)
    data["lst_tvl"] = _format_number(data.get("lst_tvl"), decimals=0)
    data["lst_cap"] = _format_number(data.get("lst_cap"), decimals=0)
    data["lst_apy"] = _format_number(data.get("lst_apy"), decimals=2)

    # ---------- 3️⃣ BARRE DE PROGRESSION ----------
    try:
        tvl_float = float(str(data.get("lst_tvl")).replace(",", ""))
        cap_float = float(str(data.get("lst_cap")).replace(",", ""))
        suffix = "$USDC" if asset.get("asset_ticker") == "USDC" else ""
        data["capacity_bar"] = generate_progress_bar(
            current=tvl_float,
            maximum=cap_float,
            length=20,
            suffix=suffix,
            decimals=2,
        )
    except Exception:
        data["capacity_bar"] = "N/A"

    # ---------- 4️⃣ NOM D'ACTIF PERSONNALISÉ ----------
    ticker = asset.get("asset_ticker", "")
    data["asset_name"] = _pretty_asset_name(ticker)

    # ---------- 5️⃣ FUSION CONTEXTE ----------
    context = _merge_prev_into_context(current=data, prev=prev)

    # ---------- 6️⃣ FORMATAGE DES MONTANTS CAP (avec virgules) ----------
    for key in ("lst_cap", "prev.lst_cap"):
        if key in context:
            try:
                num = float(context[key])
                sign = "+" if num >= 0 else "-"
                context[key] = f"{sign}{abs(int(round(num))):,}"
            except (ValueError, TypeError):
                pass

    # ---------- 7️⃣ EN‑TÊTE DYNAMIQUE POUR TVL_CHANGE ----------
    # Le template `tvl_change` contient la ligne statique :
    #   "{{tvl_icon}} Capacity changed"
    # Nous la remplaçons par un placeholder que nous remplissons ici.
    tmpl = tmpl.replace(
        "{{tvl_icon}} Capacity changed",
        "{{tvl_header}}"
    )

    # Déterminer le sens du changement de TVL (déjà présent dans context sous la forme "+xxx.xx" ou "-xxx.xx")
    tvl_diff_raw = context.get("tvl_diff", "")
    if isinstance(tvl_diff_raw, str) and tvl_diff_raw.startswith("-"):
        context["tvl_header"] = "📉 Withdrawal"
    else:
        # Tout ce qui n’est pas négatif (positif ou absent) est considéré comme dépôt
        context["tvl_header"] = "📈 Deposit"

    # ---------- 8️⃣ TRAITEMENT SPÉCIAL DES CHAMPS *_diff ----------
    for key in list(context.keys()):
        if not key.endswith("_diff"):
            continue

        # cap_diff déjà formaté → on le laisse tel quel
        if key == "cap_diff":
            continue

        # tvl_diff : icône déjà géré via le header, on garde le format numérique
        if key == "tvl_diff":
            try:
                num = float(context[key])
                context[key] = f"{num:+,.2f}"
            except (ValueError, TypeError):
                pass
            continue

        # Tous les autres *_diff (epoch_change, etc.)
        try:
            num = float(context[key])
            context[key] = f"{num:+,.2f}"
        except (ValueError, TypeError):
            pass

    # ---------- 9️⃣ REMPLACEMENT DES PLACEHOLDERS ----------
    rendered = tmpl
    for key, val in context.items():
        placeholder = f"{{{{{key}}}}}"
        rendered = rendered.replace(placeholder, str(val))

    # Nettoyage des placeholders non remplis
    rendered = re.sub(r"\{\{.*?\}\}", "", rendered)

    # Séparer le symbole "$" collé au nombre (ex. "400$" → "400 $")
    rendered = re.sub(r"(\d+)\$", r"\1 $", rendered)

    # ---------- 🔚 CONSTRUCTION DE L’EMBED ----------
    embed = discord.Embed(description=rendered, colour=0x2C8FFF)

    thumb_url = asset.get("asset_icon") or asset.get("lst_icon")
    if thumb_url:
        embed.set_thumbnail(url=thumb_url)

    embed.set_footer(text=f"Ticker : {asset.get('asset_ticker', 'unknown')}")
    return embed