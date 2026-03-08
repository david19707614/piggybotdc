import asyncio
import json
import os

import aiohttp
import pytest
import pytest_asyncio

from utils.fetcher import FetchError, load_assets, load_assets_with_retry


# ── load_assets (test mode) ─────────────────────────────────────────

class TestLoadAssetsTestMode:
    @pytest.mark.asyncio
    async def test_returns_dict_keyed_by_ticker(self):
        result = await load_assets(test_mode=True)
        assert isinstance(result, dict)
        assert "USDC" in result
        assert "SPYx" in result
        assert "JITOSOL" in result

    @pytest.mark.asyncio
    async def test_filters_by_asset_ticker(self):
        result = await load_assets(test_mode=True)
        for ticker, asset in result.items():
            assert asset["asset_ticker"] == ticker

    @pytest.mark.asyncio
    async def test_session_not_required_in_test_mode(self):
        """test_mode should work without a session."""
        result = await load_assets(test_mode=True, session=None)
        assert len(result) > 0


# ── load_assets (live mode) ─────────────────────────────────────────

class TestLoadAssetsLiveMode:
    @pytest.mark.asyncio
    async def test_missing_session_raises(self):
        with pytest.raises(FetchError, match="ClientSession is required"):
            await load_assets(test_mode=False, session=None)

    @pytest.mark.asyncio
    async def test_non_200_raises(self, aiohttp_mock_session_factory):
        session = aiohttp_mock_session_factory(status=500, body="error")
        with pytest.raises(FetchError, match="HTTP 500"):
            await load_assets(test_mode=False, session=session)

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self, aiohttp_mock_session_factory):
        session = aiohttp_mock_session_factory(status=200, body="not json",
                                               content_type="text/plain")
        with pytest.raises(FetchError, match="Invalid JSON"):
            await load_assets(test_mode=False, session=session)


# ── load_assets_with_retry ──────────────────────────────────────────

class TestLoadAssetsWithRetry:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self):
        result = await load_assets_with_retry(test_mode=True)
        assert "USDC" in result

    @pytest.mark.asyncio
    async def test_raises_after_all_attempts_fail(self,
                                                  aiohttp_mock_session_factory):
        session = aiohttp_mock_session_factory(status=500, body="err")
        with pytest.raises(FetchError):
            await load_assets_with_retry(test_mode=False, session=session,
                                         attempts=2)


# ── fixtures for HTTP mocking ───────────────────────────────────────

class _FakeResponse:
    """Minimal aiohttp response stub."""
    def __init__(self, status, body, content_type):
        self.status = status
        self._body = body
        self._content_type = content_type

    async def json(self):
        if self._content_type != "application/json":
            raise aiohttp.ContentTypeError(
                request_info=aiohttp.RequestInfo(
                    url="http://fake", method="GET",
                    headers={}, real_url="http://fake",
                ),
                history=(),
            )
        return json.loads(self._body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeSession:
    def __init__(self, status, body, content_type):
        self._status = status
        self._body = body
        self._content_type = content_type

    def get(self, url, **kwargs):
        return _FakeResponse(self._status, self._body, self._content_type)


@pytest.fixture()
def aiohttp_mock_session_factory():
    def _factory(*, status=200, body="[]", content_type="application/json"):
        return _FakeSession(status, body, content_type)
    return _factory
