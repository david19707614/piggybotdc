# -------------------------------------------------
# Imports
# -------------------------------------------------
import asyncio
import json
import os
import tempfile

import aiohttp
import discord
import yaml
from discord.ext import commands, tasks
from dotenv import load_dotenv
from loguru import logger

from utils.comparer import detect_changes
from utils.enricher import enrich_asset_for_change
from utils.fetcher import FetchError, load_assets_with_retry
from utils.formatter import build_embed
from utils.vault_detector import detect_new_vaults, find_vault_assets

# -------------------------------------------------
# Environment
# -------------------------------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# -------------------------------------------------
# Constants
# -------------------------------------------------
SNAPSHOT_PATH = os.path.join("data", "last_snapshot.json")
KNOWN_VAULTS_PATH = os.path.join("data", "known_vaults.json")
TICKERS = ["USDC", "SPYx", "JITOSOL"]


# -------------------------------------------------
# Snapshot helpers
# -------------------------------------------------
def _load_snapshot_from_disk() -> dict:
    if not os.path.isfile(SNAPSHOT_PATH):
        return {}
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load snapshot from disk: {}", exc)
        return {}


def _save_snapshot_to_disk(snapshot: dict) -> None:
    """Atomic write: write to a temp file in the same dir, then os.replace."""
    try:
        dir_name = os.path.dirname(SNAPSHOT_PATH) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, SNAPSHOT_PATH)
        except BaseException:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        logger.error("Failed to save snapshot: {}", exc)


# -------------------------------------------------
# Known vaults persistence
# -------------------------------------------------
def _load_known_vaults() -> set[str]:
    if not os.path.isfile(KNOWN_VAULTS_PATH):
        return set()
    try:
        with open(KNOWN_VAULTS_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception as exc:
        logger.warning("Failed to load known vaults: {}", exc)
        return set()


def _save_known_vaults(tickers: set[str]) -> None:
    try:
        dir_name = os.path.dirname(KNOWN_VAULTS_PATH) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(sorted(tickers), f)
            os.replace(tmp_path, KNOWN_VAULTS_PATH)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        logger.error("Failed to save known vaults: {}", exc)


# -------------------------------------------------
# Admin check
# -------------------------------------------------
def is_admin(ctx: commands.Context) -> bool:
    return ctx.author.id == ADMIN_ID


# -------------------------------------------------
# Cog
# -------------------------------------------------
class PiggyBotCog(commands.Cog):
    def __init__(self, bot: "PiggyBot") -> None:
        self.bot = bot
        self.prev_snapshot: dict = {}
        self.channel: discord.TextChannel | None = None
        self.session: aiohttp.ClientSession | None = None
        self.templates: dict = {}
        self.known_vault_tickers: set[str] = set()

    # -- lifecycle ------------------------------------------------

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession()
        with open("config/template.yaml", "r", encoding="utf-8") as f:
            self.templates = yaml.safe_load(f)
        self.prev_snapshot = _load_snapshot_from_disk()
        if self.prev_snapshot:
            logger.info("Snapshot loaded from {} ({} assets)",
                        SNAPSHOT_PATH, len(self.prev_snapshot))
        else:
            logger.info("No existing snapshot — starting with empty state")

        self.known_vault_tickers = _load_known_vaults()
        if self.known_vault_tickers:
            logger.info("Known vaults loaded: {}", self.known_vault_tickers)

    async def cog_unload(self) -> None:
        self.poll_loop.cancel()
        if self.prev_snapshot:
            _save_snapshot_to_disk(self.prev_snapshot)
            logger.info("Snapshot flushed to disk on shutdown")
        if self.known_vault_tickers:
            _save_known_vaults(self.known_vault_tickers)
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("HTTP session closed")

    # -- events ---------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        logger.info("Bot ready — logged in as {}", self.bot.user)
        self.channel = self.bot.get_channel(CHANNEL_ID)
        if self.channel is None:
            try:
                self.channel = await self.bot.fetch_channel(CHANNEL_ID)
            except (discord.NotFound, discord.Forbidden) as exc:
                logger.error("Cannot access channel {}: {}", CHANNEL_ID, exc)
        if self.channel:
            logger.info("Target channel: #{}", self.channel.name)
        else:
            logger.warning("Target channel not found — notifications disabled")

        # Sync slash commands
        try:
            synced = await self.bot.tree.sync()
            logger.info("Synced {} slash commands", len(synced))
        except Exception as exc:
            logger.error("Failed to sync slash commands: {}", exc)

        if not self.poll_loop.is_running():
            self.poll_loop.start()

    # -- polling --------------------------------------------------

    @tasks.loop(seconds=30)
    async def poll_loop(self) -> None:
        if self.channel is None:
            return

        try:
            assets = await load_assets_with_retry(
                test_mode=TEST_MODE, session=self.session
            )
        except FetchError:
            # Already logged inside load_assets_with_retry
            return

        # -- new vault detection --
        if not self.known_vault_tickers:
            # First run: seed from current data, don't announce
            self.known_vault_tickers = find_vault_assets(assets)
            _save_known_vaults(self.known_vault_tickers)
            logger.info("Seeded known vaults: {}", self.known_vault_tickers)
        else:
            new_vaults = detect_new_vaults(assets, self.known_vault_tickers)
            for ticker in new_vaults:
                logger.info("New vault detected: {}", ticker)
                embed = build_embed(
                    tmpl=self.templates["new_vault"],
                    asset=assets[ticker],
                    prev={},
                )
                await self.channel.send(embed=embed)
                self.known_vault_tickers.add(ticker)
            if new_vaults:
                _save_known_vaults(self.known_vault_tickers)

        current = {t: assets[t] for t in TICKERS if t in assets}
        changes = detect_changes(self.prev_snapshot, current)

        for ticker, change_list in changes.items():
            for change_type in change_list:
                enrich_asset_for_change(change_type, ticker, current,
                                        self.prev_snapshot)
                embed = build_embed(
                    tmpl=self.templates[change_type],
                    asset=current[ticker],
                    prev=self.prev_snapshot.get(ticker, {}),
                )
                await self.channel.send(embed=embed)

        self.prev_snapshot = current.copy()
        _save_snapshot_to_disk(self.prev_snapshot)

    # -- hybrid commands ------------------------------------------

    @commands.hybrid_command(name="usdc", description="Show USDC vault stats")
    async def cmd_usdc(self, ctx: commands.Context) -> None:
        await self._show_asset(ctx, "USDC")

    @commands.hybrid_command(name="spyx", description="Show SPYx vault stats")
    async def cmd_spyx(self, ctx: commands.Context) -> None:
        await self._show_asset(ctx, "SPYx")

    @commands.hybrid_command(name="jitosol",
                             description="Show JITOSOL vault stats")
    async def cmd_jitosol(self, ctx: commands.Context) -> None:
        await self._show_asset(ctx, "JITOSOL")

    @commands.hybrid_command(name="status",
                             description="Show all tracked assets")
    async def cmd_status(self, ctx: commands.Context) -> None:
        if not self.prev_snapshot:
            await ctx.send("No data available yet.")
            return
        for ticker, asset in self.prev_snapshot.items():
            embed = build_embed(
                tmpl=self.templates["status"],
                asset=asset,
                prev={},
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="reload",
                             description="Reload YAML templates (admin only)")
    @commands.check(is_admin)
    async def cmd_reload(self, ctx: commands.Context) -> None:
        with open("config/template.yaml", "r", encoding="utf-8") as f:
            self.templates = yaml.safe_load(f)
        await ctx.send("Templates reloaded.")

    # -- helper ---------------------------------------------------

    async def _show_asset(self, ctx: commands.Context, ticker: str) -> None:
        try:
            assets = await load_assets_with_retry(
                test_mode=TEST_MODE, session=self.session
            )
        except FetchError as exc:
            await ctx.send(f"Failed to fetch data: {exc}")
            return

        asset = assets.get(ticker)
        if not asset:
            await ctx.send(f"No data found for `{ticker}`.")
            return

        embed = build_embed(
            tmpl=self.templates["stats"],
            asset=asset,
            prev={},
        )
        await ctx.send(embed=embed)


# -------------------------------------------------
# Bot subclass
# -------------------------------------------------
class PiggyBot(commands.Bot):
    async def close(self) -> None:
        for name in list(self.cogs):
            await self.remove_cog(name)
        await super().close()


# -------------------------------------------------
# Main
# -------------------------------------------------
async def main() -> None:
    intents = discord.Intents.default()
    intents.message_content = True

    bot = PiggyBot(command_prefix="!", intents=intents)
    await bot.add_cog(PiggyBotCog(bot))

    try:
        await bot.start(TOKEN)
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
