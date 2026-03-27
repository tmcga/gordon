"""Event types for the event-driven pipeline.

The core flow: MarketEvent -> SignalEvent -> OrderEvent -> FillEvent
Each event is a frozen Pydantic model carrying the data needed by downstream handlers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from gordon.core.models import Bar, Fill, Order, Signal  # noqa: TC001


class Event(BaseModel, frozen=True):
    """Base event with a timestamp."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.event_type:
            object.__setattr__(self, "event_type", self.__class__.__name__)


class MarketEvent(Event):
    """New market data arrived."""

    bar: Bar


class SignalEvent(Event):
    """A strategy produced a trading signal."""

    signal: Signal


class OrderEvent(Event):
    """An order has been created and should be routed to the broker."""

    order: Order


class FillEvent(Event):
    """An order was filled (fully or partially)."""

    fill: Fill
