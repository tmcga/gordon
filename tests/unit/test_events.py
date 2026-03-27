"""Tests for gordon.core.events — event types for the pipeline."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from gordon.core.enums import (
    Side,
)
from gordon.core.events import (
    Event,
    FillEvent,
    MarketEvent,
    OrderEvent,
    SignalEvent,
)
from gordon.core.models import (
    Signal,
)

# ── Event (base) ──────────────────────────────────────────────────────


class TestEvent:
    def test_default_timestamp(self):
        event = Event()
        assert isinstance(event.timestamp, datetime)

    def test_event_type_auto_set(self):
        event = Event()
        assert event.event_type == "Event"

    def test_custom_timestamp(self):
        ts = datetime(2025, 6, 1, 12, 0, 0)
        event = Event(timestamp=ts)
        assert event.timestamp == ts
        assert event.event_type == "Event"

    def test_frozen(self):
        event = Event()
        with pytest.raises(ValidationError):
            event.event_type = "something"


# ── MarketEvent ────────────────────────────────────────────────────────


class TestMarketEvent:
    def test_creation(self, sample_bar):
        event = MarketEvent(bar=sample_bar)
        assert event.bar == sample_bar
        assert event.event_type == "MarketEvent"
        assert isinstance(event.timestamp, datetime)

    def test_frozen(self, sample_bar):
        event = MarketEvent(bar=sample_bar)
        with pytest.raises(ValidationError):
            event.bar = sample_bar

    def test_requires_bar(self):
        with pytest.raises(ValidationError):
            MarketEvent()


# ── SignalEvent ────────────────────────────────────────────────────────


class TestSignalEvent:
    def test_creation(self, sample_asset):
        signal = Signal(
            asset=sample_asset,
            side=Side.BUY,
            strength=0.75,
            strategy_id="test",
        )
        event = SignalEvent(signal=signal)
        assert event.signal == signal
        assert event.event_type == "SignalEvent"

    def test_frozen(self, sample_asset):
        signal = Signal(asset=sample_asset, side=Side.BUY, strength=0.5, strategy_id="s")
        event = SignalEvent(signal=signal)
        with pytest.raises(ValidationError):
            event.signal = signal

    def test_requires_signal(self):
        with pytest.raises(ValidationError):
            SignalEvent()


# ── OrderEvent ─────────────────────────────────────────────────────────


class TestOrderEvent:
    def test_creation(self, sample_order):
        event = OrderEvent(order=sample_order)
        assert event.order == sample_order
        assert event.event_type == "OrderEvent"

    def test_frozen(self, sample_order):
        event = OrderEvent(order=sample_order)
        with pytest.raises(ValidationError):
            event.order = sample_order

    def test_requires_order(self):
        with pytest.raises(ValidationError):
            OrderEvent()


# ── FillEvent ──────────────────────────────────────────────────────────


class TestFillEvent:
    def test_creation(self, sample_fill):
        event = FillEvent(fill=sample_fill)
        assert event.fill == sample_fill
        assert event.event_type == "FillEvent"

    def test_frozen(self, sample_fill):
        event = FillEvent(fill=sample_fill)
        with pytest.raises(ValidationError):
            event.fill = sample_fill

    def test_requires_fill(self):
        with pytest.raises(ValidationError):
            FillEvent()
