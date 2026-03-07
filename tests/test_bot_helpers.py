import json
import os
import tempfile

import pytest


# We test the snapshot helpers directly; they're module-level functions in bot.py.
# Import them by reaching into the module.  bot.py reads env vars at import time,
# so we set minimal values before importing.

@pytest.fixture(autouse=True)
def _patch_env(monkeypatch):
    """Provide dummy env vars so bot.py can be imported without a .env file."""
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("ADMIN_ID", "111111111")


@pytest.fixture()
def snapshot_file(tmp_path):
    """Yield a temporary snapshot file path and patch SNAPSHOT_PATH."""
    path = tmp_path / "last_snapshot.json"
    return path


class TestSaveSnapshotToDisk:
    def test_creates_file(self, snapshot_file, monkeypatch):
        # Import after env is patched
        import bot
        monkeypatch.setattr(bot, "SNAPSHOT_PATH", str(snapshot_file))
        data = {"USDC": {"epoch": 63}}
        bot._save_snapshot_to_disk(data)
        assert snapshot_file.exists()
        assert json.loads(snapshot_file.read_text()) == data

    def test_overwrites_existing(self, snapshot_file, monkeypatch):
        import bot
        monkeypatch.setattr(bot, "SNAPSHOT_PATH", str(snapshot_file))
        bot._save_snapshot_to_disk({"v": 1})
        bot._save_snapshot_to_disk({"v": 2})
        assert json.loads(snapshot_file.read_text()) == {"v": 2}

    def test_atomic_no_partial_on_error(self, snapshot_file, monkeypatch):
        """If serialisation fails the original file should be untouched."""
        import bot
        monkeypatch.setattr(bot, "SNAPSHOT_PATH", str(snapshot_file))
        bot._save_snapshot_to_disk({"good": True})

        # Try to write something that will fail (non-serialisable)
        class Bad:
            pass
        bot._save_snapshot_to_disk({"bad": Bad()})

        # Original content should still be intact
        assert json.loads(snapshot_file.read_text()) == {"good": True}


class TestLoadSnapshotFromDisk:
    def test_returns_empty_when_missing(self, snapshot_file, monkeypatch):
        import bot
        monkeypatch.setattr(bot, "SNAPSHOT_PATH", str(snapshot_file))
        assert bot._load_snapshot_from_disk() == {}

    def test_loads_valid_json(self, snapshot_file, monkeypatch):
        import bot
        monkeypatch.setattr(bot, "SNAPSHOT_PATH", str(snapshot_file))
        data = {"USDC": {"epoch": 63}}
        snapshot_file.write_text(json.dumps(data))
        assert bot._load_snapshot_from_disk() == data

    def test_returns_empty_on_corrupt_json(self, snapshot_file, monkeypatch):
        import bot
        monkeypatch.setattr(bot, "SNAPSHOT_PATH", str(snapshot_file))
        snapshot_file.write_text("{broken json")
        assert bot._load_snapshot_from_disk() == {}


class TestIsAdmin:
    def test_admin_returns_true(self, monkeypatch):
        import bot
        monkeypatch.setattr(bot, "ADMIN_ID", 42)

        class FakeCtx:
            class author:
                id = 42
        assert bot.is_admin(FakeCtx()) is True

    def test_non_admin_returns_false(self, monkeypatch):
        import bot
        monkeypatch.setattr(bot, "ADMIN_ID", 42)

        class FakeCtx:
            class author:
                id = 99
        assert bot.is_admin(FakeCtx()) is False
