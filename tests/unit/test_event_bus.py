"""Tests for the async EventBus."""

from __future__ import annotations

import pytest

from gordon.core.events import Event, FillEvent, MarketEvent
from gordon.engine.event_bus import EventBus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_market_event():
    """Create a minimal MarketEvent for testing."""
    from datetime import datetime
    from decimal import Decimal

    from gordon.core.enums import AssetClass, Interval
    from gordon.core.models import Asset, Bar

    asset = Asset(symbol="TEST", asset_class=AssetClass.EQUITY)
    bar = Bar(
        asset=asset,
        timestamp=datetime(2025, 1, 1),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=Decimal("1000"),
        interval=Interval.D1,
    )
    return MarketEvent(bar=bar)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_emit(self):
        bus = EventBus()
        received: list[Event] = []

        def handler(event):
            received.append(event)

        bus.subscribe(MarketEvent, handler)
        evt = _make_market_event()
        await bus.emit(evt)

        assert len(received) == 1
        assert received[0] is evt

    @pytest.mark.asyncio
    async def test_async_handler(self):
        bus = EventBus()
        received: list[Event] = []

        async def handler(event):
            received.append(event)

        bus.subscribe(MarketEvent, handler)
        await bus.emit(_make_market_event())
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_multiple_handlers(self):
        bus = EventBus()
        calls: list[str] = []

        def h1(event):
            calls.append("h1")

        def h2(event):
            calls.append("h2")

        bus.subscribe(MarketEvent, h1)
        bus.subscribe(MarketEvent, h2)
        await bus.emit(_make_market_event())
        assert calls == ["h1", "h2"]

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        bus = EventBus()
        calls: list[str] = []

        def handler(event):
            calls.append("called")

        bus.subscribe(MarketEvent, handler)
        bus.unsubscribe(MarketEvent, handler)
        await bus.emit(_make_market_event())
        assert calls == []

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_is_safe(self):
        bus = EventBus()

        def handler(event):
            pass

        # Should not raise
        bus.unsubscribe(MarketEvent, handler)

    @pytest.mark.asyncio
    async def test_no_cross_event_dispatch(self):
        """Handlers for one event type should not receive events of another type."""
        bus = EventBus()
        received: list[Event] = []

        def handler(event):
            received.append(event)

        bus.subscribe(FillEvent, handler)
        await bus.emit(_make_market_event())
        assert received == []

    @pytest.mark.asyncio
    async def test_handler_error_does_not_stop_others(self):
        bus = EventBus()
        calls: list[str] = []

        def bad_handler(event):
            raise ValueError("boom")

        def good_handler(event):
            calls.append("ok")

        bus.subscribe(MarketEvent, bad_handler)
        bus.subscribe(MarketEvent, good_handler)
        await bus.emit(_make_market_event())
        assert calls == ["ok"]

    @pytest.mark.asyncio
    async def test_duplicate_subscribe_ignored(self):
        bus = EventBus()
        calls = []

        def handler(event):
            calls.append(1)

        bus.subscribe(MarketEvent, handler)
        bus.subscribe(MarketEvent, handler)  # duplicate
        await bus.emit(_make_market_event())
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_clear(self):
        bus = EventBus()
        calls = []

        def handler(event):
            calls.append(1)

        bus.subscribe(MarketEvent, handler)
        bus.clear()
        await bus.emit(_make_market_event())
        assert calls == []
