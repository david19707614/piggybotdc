# -------------------------------------------------
# Imports
# -------------------------------------------------
import asyncio
import json
import os
import tempfile
from datetime import datetime, time, timezone

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
from utils.recap import build_recap_lines, empty_recap_state, record_changes

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
RECAP_PATH = os.path.join("data", "recap_state.json")
TICKERS = ["USDC", "SPYx", "JITOSOL"]

DAILY_RECAP_HOUR = int(os.getenv("DAILY_RECAP_HOUR", "0"))   # UTC
WEEKLY_RECAP_DAY = int(os.getenv("WEEKLY_RECAP_DAY", "0"))    # 0=Monday


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
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        logger.error("Failed to save snapshot: {}", exc)


# -------------------------------------------------
# Recap state persistence
# -------------------------------------------------
def _load_recap_state() -> dict:
    if not os.path.isfile(RECAP_PATH):
        return {}
    try:
        with open(RECAP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load recap state: {}", exc)
        return {}


def _save_recap_state(state: dict) -> None:
    try:
        dir_name = os.path.dirname(RECAP_PATH) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, RECAP_PATH)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        logger.error("Failed to save recap state: {}", exc)


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
        self.daily_state: dict = {}
        self.weekly_state: dict = {}

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

        saved = _load_recap_state()
        self.daily_state = saved.get("daily", empty_recap_state())
        self.weekly_state = saved.get("weekly", empty_recap_state())

    async def cog_unload(self) -> None:
        self.poll_loop.cancel()
        self.recap_tick.cancel()
        if self.prev_snapshot:
            _save_snapshot_to_disk(self.prev_snapshot)
            logger.info("Snapshot flushed to disk on shutdown")
        _save_recap_state({
            "daily": self.daily_state,
            "weekly": self.weekly_state,
        })
        logger.info("Recap state flushed to disk on shutdown")
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

        try:
            synced = await self.bot.tree.sync()
            logger.info("Synced {} slash commands", len(synced))
        except Exception as exc:
            logger.error("Failed to sync slash commands: {}", exc)

        if not self.poll_loop.is_running():
            self.poll_loop.start()
        if not self.recap_tick.is_running():
            self.recap_tick.start()

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
            return

        current = {t: assets[t] for t in TICKERS if t in assets}
        changes = detect_changes(self.prev_snapshot, current)

        # Track changes for recaps
        if changes:
            record_changes(self.daily_state, changes, current)
            record_changes(self.weekly_state, changes, current)
            _save_recap_state({
                "daily": self.daily_state,
                "weekly": self.weekly_state,
            })

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

    # -- recap scheduling -----------------------------------------

    @tasks.loop(minutes=1)
    async def recap_tick(self) -> None:
        """Check once per minute whether it's time to post a recap."""
        if self.channel is None:
            return

        now = datetime.now(timezone.utc)

        # Daily recap: fire at the configured hour, minute 0
        if now.hour == DAILY_RECAP_HOUR and now.minute == 0:
            await self._post_recap("daily")

        # Weekly recap: fire on the configured weekday at the same hour
        if (now.weekday() == WEEKLY_RECAP_DAY
                and now.hour == DAILY_RECAP_HOUR and now.minute == 0):
            await self._post_recap("weekly")

    async def _post_recap(self, kind: str) -> None:
        state = self.daily_state if kind == "daily" else self.weekly_state
        lines = build_recap_lines(state)
        body = "\n".join(lines)

        if kind == "daily":
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            tmpl = self.templates.get("daily_recap", "{{recap_body}}")
            rendered = tmpl.replace("{{date}}", date_str)
        else:
            start = state.get("period_start", "?")
            end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            tmpl = self.templates.get("weekly_recap", "{{recap_body}}")
            rendered = tmpl.replace("{{week_range}}", f"{start[:10]} — {end}")

        rendered = rendered.replace("{{recap_body}}", body)

        embed = discord.Embed(description=rendered, colour=0x2C8FFF)
        await self.channel.send(embed=embed)
        logger.info("{} recap posted", kind.capitalize())

        # Reset the state
        if kind == "daily":
            self.daily_state = empty_recap_state()
        else:
            self.weekly_state = empty_recap_state()

        _save_recap_state({
            "daily": self.daily_state,
            "weekly": self.weekly_state,
        })

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

    @commands.hybrid_command(name="recap",
                             description="Show accumulated stats since last recap")
    async def cmd_recap(self, ctx: commands.Context) -> None:
        lines = build_recap_lines(self.daily_state)
        body = "\n".join(lines)
        start = self.daily_state.get("period_start", "?")[:10]
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        header = f"📋 **Recap** ({start} — {now_str})\n\n"
        embed = discord.Embed(description=header + body, colour=0x2C8FFF)
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
