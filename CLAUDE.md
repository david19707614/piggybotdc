# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PiggyBotDC is a Discord bot (Python) that monitors three DeFi vault assets on PiggyBank.fi (Solana-based). It polls the PiggyBank API every 30 seconds and posts Discord embed notifications when vault metrics change (epoch, capacity, or TVL).

Tracked assets: USDC, SPYx (S&P 500 token), JITOSOL (Jito SOL).

## Commands

```bash
pip install -r requirements.txt   # Install dependencies
python bot.py                     # Run the bot
python -m pytest tests/ -v        # Run test suite
```

Set `TEST_MODE=true` in `.env` to use `data/test-assets.json` instead of the live API.

## Required Environment Variables (.env)

- `DISCORD_BOT_TOKEN` — Bot token from Discord Developer Portal
- `DISCORD_CHANNEL_ID` — Channel ID for posting notifications
- `ADMIN_ID` — Discord user ID allowed to use `!reload`
- `TEST_MODE` — Optional, set `"true"` to use mock data

The bot requires the `message_content` intent enabled in the Discord Developer Portal.

## Architecture

**Entry point:** `bot.py` — `PiggyBot(commands.Bot)` subclass + `PiggyBotCog(commands.Cog)` that owns all mutable state. Launched via `asyncio.run(main())`.

**Pipeline per poll cycle:**
1. `utils/fetcher.py` → `load_assets_with_retry()` fetches from the PiggyBank API with retry/backoff (or reads local JSON in test mode), returns `dict[ticker -> asset_dict]`
2. `utils/comparer.py` → `detect_changes(old, new)` compares snapshots, returns `dict[ticker -> list[change_type]]` where change types are `epoch_change`, `cap_change`, `tvl_change`
3. `utils/enricher.py` → `enrich_asset_for_change()` injects computed diff fields (`cap_diff`, `tvl_diff`, `tvl_emoji`, `epoch_change`) into the asset dict
4. `utils/formatter.py` → `build_embed()` takes a YAML template + asset dict, performs numeric formatting, generates a Unicode progress bar, and returns a `discord.Embed`
5. State persisted atomically to `data/last_snapshot.json` after each cycle (survives restarts)

**Template system** (`config/template.yaml`):
- `{{key}}` mustache-style placeholders with template blocks per change type (`epoch_change`, `cap_change`, `tvl_change`, `stats`, `status`)
- Special placeholders: `{{capacity_bar}}` (progress bar), `{{tvl_icon}}` (trend arrow), `{{tvl_emoji}}` (size-based emoji)
- Previous-state access via `{{prev.xxx}}` placeholders

**Discord commands** — hybrid commands (`!usdc`/`/usdc`, `!spyx`/`/spyx`, `!jitosol`/`/jitosol`, `!status`/`/status`, `!reload`/`/reload`) registered via `PiggyBotCog`. Slash commands synced on `on_ready`.

## Notable Details

- `config/commands.yaml` is reference-only documentation.
- `utils/formatter.py.old` is an unused prior version of the formatter.
- Logging uses loguru (`from loguru import logger`).
- Python 3.11+ required (union type syntax `X | None`).
