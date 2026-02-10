# -------------------------------------------------
# Imports
# -------------------------------------------------
import os
import json                     # <-- pour persister le snapshot
import yaml
import discord
from discord.ext import tasks, commands
from dotenv import load_dotenv
import functools               # (facultatif, on garde pour d’éventuels usages)

from utils.fetcher import load_assets
from utils.comparer import detect_changes
from utils.formatter import build_embed

# -------------------------------------------------
# 1️⃣ Chargement du .env
# -------------------------------------------------
load_dotenv()
TOKEN          = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID     = int(os.getenv("DISCORD_CHANNEL_ID"))
TEST_MODE      = os.getenv("TEST_MODE", "false").lower() == "true"
ADMIN_ID       = int(os.getenv("ADMIN_ID"))

# -------------------------------------------------
# 2️⃣ Templates (template.yaml)
# -------------------------------------------------
with open("config/template.yaml", "r", encoding="utf-8") as f:
    TEMPLATES = yaml.safe_load(f)

# -------------------------------------------------
# 3️⃣ Intents – indispensable pour les préfixes
# -------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True          # <‑‑ obligatoire pour les commandes !…
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------------------------------
# 4️⃣ Mapping commande → ticker (en‑code)
# -------------------------------------------------
COMMAND_MAP = {
    "USDC":    "USDC",
    "SPYX":    "SPYx",
    "JITOSOL": "JITOSOL",
}

# -------------------------------------------------
# 5️⃣ Chemin du fichier de persistance
# -------------------------------------------------
SNAPSHOT_PATH = os.path.join("data", "last_snapshot.json")

# -------------------------------------------------
# 6️⃣ Helper admin
# -------------------------------------------------
def is_admin(ctx):
    return ctx.author.id == ADMIN_ID

# -------------------------------------------------
# 7️⃣ Commande admin – reload des templates (facultatif)
# -------------------------------------------------
@bot.command(name="reload")
@commands.check(is_admin)
async def reload_templates(ctx):
    """Recharge les templates YAML sans redémarrer le bot."""
    global TEMPLATES
    with open("config/template.yaml", "r", encoding="utf-8") as f:
        TEMPLATES = yaml.safe_load(f)
    await ctx.send("✅ Templates rechargés.")

# -------------------------------------------------
# 8️⃣ Fonction utilitaire pour récupérer le channel (cache + fetch)
# -------------------------------------------------
async def get_target_channel():
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        return channel
    try:
        return await bot.fetch_channel(CHANNEL_ID)
    except (discord.NotFound, discord.Forbidden) as e:
        print(f"⚠️ Impossible d'accéder au channel {CHANNEL_ID}: {e}")
        return None

# -------------------------------------------------
# 9️⃣ Factory qui crée une coroutine pour chaque ticker
# -------------------------------------------------
def make_asset_command(ticker: str):
    async def _cmd(ctx):
        assets = await load_assets(test_mode=TEST_MODE)
        asset = assets.get(ticker)
        if not asset:
            await ctx.send(f"❓ Aucun asset trouvé pour `{ticker}`.")
            return

        embed = build_embed(
            tmpl=TEMPLATES["stats"],   # bloc "stats" du template.yaml
            asset=asset,
            prev={}
        )
        await ctx.send(embed=embed)

    return _cmd

# -------------------------------------------------
# 10️⃣ Enregistrement dynamique des trois commandes publiques
# -------------------------------------------------
for cmd_name, ticker in COMMAND_MAP.items():
    callback = make_asset_command(ticker)
    callback.__name__ = f"cmd_{cmd_name.lower()}"
    bot.add_command(commands.Command(callback, name=cmd_name.lower()))

# -------------------------------------------------
# 11️⃣ Commande publique : !status (affiche le snapshot chargé)
# -------------------------------------------------
@bot.command(name="status")
async def status_all(ctx):
    """
    Renvoie un embed **pour chaque asset suivi** contenant les informations
    actuelles (epoch, lst_cap, lst_tvl, lst_apy, etc.).
    """
    # Le snapshot chargé (ou vide) est stocké dans `prev_snapshot`
    if not prev_snapshot:
        await ctx.send("ℹ️ Aucun état disponible pour le moment.")
        return

    for ticker, asset in prev_snapshot.items():
        embed = build_embed(
            tmpl=TEMPLATES["status"],   # le nouveau bloc que nous venons d’ajouter
            asset=asset,
            prev={}
        )
        await ctx.send(embed=embed)

# -------------------------------------------------
# 12️⃣ Variables globales du polling
# -------------------------------------------------
prev_snapshot = {}          # sera remplie au démarrage (voir on_ready)
CHANNEL_OBJ = None

# -------------------------------------------------
# 13️⃣ Fonction de sauvegarde du snapshot sur disque
# -------------------------------------------------
def save_snapshot_to_disk(snapshot: dict):
    """Écrit le dictionnaire `snapshot` dans data/last_snapshot.json."""
    try:
        with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"⚠️ Erreur lors de la sauvegarde du snapshot : {exc}")

# -------------------------------------------------
# 14️⃣ Fonction de chargement du snapshot depuis le disque
# -------------------------------------------------
def load_snapshot_from_disk() -> dict:
    """Lit le fichier JSON s’il existe, sinon renvoie un dict vide."""
    if not os.path.isfile(SNAPSHOT_PATH):
        return {}
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"⚠️ Erreur lors du chargement du snapshot : {exc}")
        return {}

# -------------------------------------------------
# 15️⃣ Tâche de polling (mise à jour + persistance)
# -------------------------------------------------
# -------------------------------------------------
# Dans bot.py – fonction poll_assets (déjà existante)
# -------------------------------------------------
@tasks.loop(seconds=30)
async def poll_assets():
    global prev_snapshot, CHANNEL_OBJ

    # 1️⃣ Résolution du channel (inchangée)
    if CHANNEL_OBJ is None:
        CHANNEL_OBJ = await get_target_channel()
        if CHANNEL_OBJ is None:
            return

    # 2️⃣ Récupération des données (API ou fichier test)
    assets = await load_assets(test_mode=TEST_MODE)

    # 3️⃣ On ne suit que les trois tickers
    tickers = ["USDC", "SPYx", "JITOSOL"]
    current = {t: assets[t] for t in tickers if t in assets}

    # 4️⃣ Détection des changements
    changes = detect_changes(prev_snapshot, current)

    # 5️⃣ **Injection des champs calculés** avant de créer les embeds
    for ticker, change_list in changes.items():
        for change_type in change_list:
            # ----- CAPACITY (lst_cap) -----
            if change_type == "cap_change":
                prev_cap = prev_snapshot.get(ticker, {}).get("lst_cap")
                cur_cap  = current[ticker].get("lst_cap")
                if prev_cap is not None and cur_cap is not None:
                    # différence absolue (positive ou négative)
                    diff = cur_cap - prev_cap
                    # on stocke deux variantes utiles
                    current[ticker]["cap_diff"] = f"{diff:+}"   # ex. "+100" ou "-20"
                    # on garde aussi la version brute au cas où le template voudrait le format décimal
                    current[ticker]["cap_diff_raw"] = diff

            # ----- TVL (lst_tvl) -----
            if change_type == "tvl_change":
                prev_tvl = prev_snapshot.get(ticker, {}).get("lst_tvl")
                cur_tvl  = current[ticker].get("lst_tvl")
                if prev_tvl is not None and cur_tvl is not None:
                    diff = cur_tvl - prev_tvl
                    current[ticker]["tvl_diff"] = f"{diff:+}"
                    current[ticker]["tvl_diff_raw"] = diff

            # ----- EPOCH -----
            if change_type == "epoch_change":
                prev_ep = prev_snapshot.get(ticker, {}).get("epoch")
                cur_ep  = current[ticker].get("epoch")
                if prev_ep is not None and cur_ep is not None:
                    current[ticker]["epoch_change"] = f"{prev_ep} → {cur_ep}"

            # ----- Construction de l’embed -----
            embed = build_embed(
                tmpl=TEMPLATES[change_type],
                asset=current[ticker],
                prev=prev_snapshot.get(ticker, {})
            )
            await CHANNEL_OBJ.send(embed=embed)

    # 6️⃣ Mise à jour du snapshot en mémoire + persistance
    prev_snapshot = current.copy()
    save_snapshot_to_disk(prev_snapshot)
# -------------------------------------------------
# 16️⃣ on_ready – charger le snapshot et démarrer le polling
# -------------------------------------------------
@bot.event
async def on_ready():
    global CHANNEL_OBJ, prev_snapshot
    print(f"✅ Bot prêt – connecté en tant que {bot.user}")

    # 1️⃣ Récupérer le channel cible (cache + fetch)
    CHANNEL_OBJ = await get_target_channel()
    if CHANNEL_OBJ is None:
        print("⚠️ Le bot n’a pas pu récupérer le channel cible ; les notifications seront silencieuses.")

    # 2️⃣ Charger le snapshot depuis le disque (s’il existe)
    prev_snapshot = load_snapshot_from_disk()
    if prev_snapshot:
        print(f"🔄 Snapshot chargé depuis {SNAPSHOT_PATH} ({len(prev_snapshot)} assets).")
    else:
        print("ℹ️ Aucun snapshot préexistant – le bot commencera avec un état vide.")

    # 3️⃣ Démarrer la boucle de polling
    poll_assets.start()

# -------------------------------------------------
# 17️⃣ Lancer le bot
# -------------------------------------------------
bot.run(TOKEN)