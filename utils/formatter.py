# utils/formatter.py
import discord
import time
import re
import os
from typing import Dict, Any

# -------------------------------------------------
# Helper – formatage numérique
# -------------------------------------------------
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


# -------------------------------------------------
# Fonction de génération de la barre de progression
# -------------------------------------------------
def generate_progress_bar(current: float, maximum: float, length: int = 20) -> str:
    """
    Retourne une barre de progression Unicode.
    - `length` : nombre de caractères de la barre (ex. 20 → 20 blocs).
    - Si `maximum` ≤ 0, renvoie « N/A ».
    - La barre est entourée de back‑ticks afin d’obtenir une police à chasse fixe dans Discord.
    """
    if maximum <= 0:
        return "N/A"

    ratio = max(0.0, min(1.0, current / maximum))
    filled_len = int(round(ratio * length))
    empty_len = length - filled_len

    filled_char = "█"   # bloc plein
    empty_char  = "░"   # bloc vide

    bar = f"{filled_char * filled_len}{empty_char * empty_len}"
    percent = int(round(ratio * 100))
    return f"`{bar}` {percent}%"


# -------------------------------------------------
# Fusion du snapshot précédent (inchangé)
# -------------------------------------------------
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


# -------------------------------------------------
# Fonction principale – build_embed
# -------------------------------------------------
def build_embed(*, tmpl: str, asset: Dict[str, Any], prev: Dict[str, Any]) -> discord.Embed:
    """
    Crée un embed à partir d’un template et d’un asset.
    - Calcule `last_epoch_seconds` et `epoch_duration`.
    - Arrondit `lst_tvl`, `lst_cap` (0 décimale) et `lst_apy` (2 décimales).
    - Formate automatiquement tout champ se terminant par `_diff` à 2 décimales,
      **sauf `cap_diff`** qui garde l’entier fourni par `bot.py`.
    - Ajoute la clé `capacity_bar` (barre de progression) et `tvl_icon`
      (📈 ou 📉) selon le signe de `tvl_diff`.
    - Fusionne les valeurs précédentes (`prev.xxx`) avec le préfixe « prev. ».
    - Nettoie les placeholders non remplis et sépare le symbole `$`.
    """
    now_ts = int(time.time())

    # ---------- 1️⃣ Calculs dérivés ----------
    epoch_start = asset.get("epoch_start")
    last_epoch_seconds = now_ts - int(epoch_start) if isinstance(epoch_start, (int, float)) else 0

    epoch_duration = None
    if prev and prev.get("epoch_start") and epoch_start is not None:
        epoch_duration = int(epoch_start) - int(prev["epoch_start"])

    # ---------- 2️⃣ Préparer les données ----------
    data = dict(asset)                     # copie superficielle
    data["last_epoch_seconds"] = last_epoch_seconds
    if epoch_duration is not None:
        data["epoch_duration"] = epoch_duration

    # Arrondissements demandés
    data["lst_tvl"] = _format_number(data.get("lst_tvl"), decimals=0)
    data["lst_cap"] = _format_number(data.get("lst_cap"), decimals=0)
    data["lst_apy"] = _format_number(data.get("lst_apy"), decimals=2)

    # ---------- 3️⃣ BARRE DE PROGRESSION ----------
    try:
        tvl_float = float(str(data.get("lst_tvl")).replace(",", ""))
        cap_float = float(str(data.get("lst_cap")).replace(",", ""))
        # Longueur de la barre peut être rendue configurable via .env
        # BAR_LEN = int(os.getenv("CAPACITY_BAR_LENGTH", "20"))
        data["capacity_bar"] = generate_progress_bar(tvl_float, cap_float, length=20)
    except Exception:
        data["capacity_bar"] = "N/A"

    # ---------- 4️⃣ Fusion avec le snapshot précédent ----------
    context = _merge_prev_into_context(current=data, prev=prev)

    # ---------- 5️⃣ Traitement spécial des champs *_diff ----------
    for key in list(context.keys()):
        if key.endswith("_diff"):
            # ---- cap_diff : on le garde tel quel (déjà formaté dans bot.py) ----
            if key == "cap_diff":
                continue

            # ---- tvl_diff : on veut aussi l’icône 📈 / 📉 ----
            if key == "tvl_diff":
                try:
                    num = float(context[key])
                    # icône selon le signe
                    if num > 0:
                        context["tvl_icon"] = "📈"
                    elif num < 0:
                        context["tvl_icon"] = "📉"
                    else:
                        context["tvl_icon"] = ""   # pas de changement
                    # on garde le format à deux décimales avec le signe
                    context[key] = f"{num:+.2f}"
                except (ValueError, TypeError):
                    context["tvl_icon"] = ""
                continue   # on a déjà traité tvl_diff, on passe au suivant

            # ---- tous les autres *_diff (epoch_change, etc.) ----
            try:
                num = float(context[key])
                context[key] = f"{num:+.2f}"
            except (ValueError, TypeError):
                pass

    # ---------- 6️⃣ Remplacement des placeholders ----------
    rendered = tmpl
    for key, val in context.items():
        placeholder = f"{{{{{key}}}}}"
        rendered = rendered.replace(placeholder, str(val))

    # Nettoyage des placeholders non remplis
    rendered = re.sub(r"\{\{.*?\}\}", "", rendered)

    # Séparer le symbole "$" collé au nombre (ex. "400$" → "400 $")
    rendered = re.sub(r"(\d+)\$", r"\1 $", rendered)

    # ---------- 7️⃣ Construction de l’embed ----------
    embed = discord.Embed(description=rendered, colour=0x2C8FFF)

    thumb_url = asset.get("asset_icon") or asset.get("lst_icon")
    if thumb_url:
        embed.set_thumbnail(url=thumb_url)

    embed.set_footer(text=f"Ticker : {asset.get('asset_ticker', 'unknown')}")
    return embed