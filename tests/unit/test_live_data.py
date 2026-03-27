"""Tests for LiveDataFeed."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gordon.data.live import _MIN_POLL_SECONDS, LiveDataFeed


@pytest.fixture()
def mock_provider() -> MagicMock:
    """A mock BaseDataFeed provider."""
    provider = MagicMock()
    provider.get_bars = AsyncMock(return_value=MagicMock(empty=True))
    return provider


class TestLiveDataFeedCreation:
    def test_creates_with_defaults(self, mock_provider: MagicMock) -> None:
        feed = LiveDataFeed(provider=mock_provider)
        assert feed._running is False
        assert feed._poll_interval >= _MIN_POLL_SECONDS

    def test_custom_poll_interval(self, mock_provider: MagicMock) -> None:
        feed = LiveDataFeed(provider=mock_provider, poll_interval=120.0)
        assert feed._poll_interval == 120.0


class TestStop:
    @pytest.mark.asyncio()
    async def test_stop_sets_running_flag(self, mock_provider: MagicMock) -> None:
        feed = LiveDataFeed(provider=mock_provider)
        feed._running = True
        await feed.stop()
        assert feed._running is False


class TestPollIntervalFloor:
    def test_interval_below_minimum_is_clamped(self, mock_provider: MagicMock) -> None:
        feed = LiveDataFeed(provider=mock_provider, poll_interval=1.0)
        assert feed._poll_interval == _MIN_POLL_SECONDS

    def test_interval_at_minimum_is_kept(self, mock_provider: MagicMock) -> None:
        feed = LiveDataFeed(provider=mock_provider, poll_interval=_MIN_POLL_SECONDS)
        assert feed._poll_interval == _MIN_POLL_SECONDS
