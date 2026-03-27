"""Domain models — the foundation every other module builds on.

All models are frozen Pydantic models: immutable, serializable, validated.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from gordon.core.enums import (
    AssetClass,
    Interval,
    OrderStatus,
    OrderType,
    Side,
    TimeInForce,
)


class Asset(BaseModel, frozen=True):
    """A tradeable instrument."""

    symbol: str
    asset_class: AssetClass
    exchange: str | None = None

    def __str__(self) -> str:
        if self.exchange:
            return f"{self.symbol}@{self.exchange}"
        return self.symbol


class Bar(BaseModel, frozen=True):
    """A single OHLCV bar."""

    asset: Asset
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    interval: Interval


class Order(BaseModel, frozen=True):
    """An order to be submitted to a broker."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    asset: Asset
    side: Side
    order_type: OrderType
    quantity: Decimal
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
    strategy_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class Fill(BaseModel, frozen=True):
    """Confirmation that an order (or part of it) was executed."""

    order_id: str
    asset: Asset
    side: Side
    price: Decimal
    quantity: Decimal
    commission: Decimal = Decimal("0")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Position(BaseModel, frozen=True):
    """A current holding in an asset."""

    asset: Asset
    quantity: Decimal  # negative = short
    avg_entry_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    @property
    def market_value(self) -> Decimal:
        return abs(self.quantity) * self.avg_entry_price


class Signal(BaseModel, frozen=True):
    """A trading signal produced by a strategy."""

    asset: Asset
    side: Side
    strength: float = Field(ge=-1.0, le=1.0)
    strategy_id: str
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioSnapshot(BaseModel, frozen=True):
    """Point-in-time snapshot of portfolio state."""

    timestamp: datetime
    cash: Decimal
    positions: tuple[Position, ...] = ()
    total_equity: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")


class TradeRecord(BaseModel, frozen=True):
    """A completed round-trip trade for analytics."""

    asset: Asset
    side: Side
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    entry_time: datetime
    exit_time: datetime
    pnl: Decimal
    commission: Decimal = Decimal("0")
    strategy_id: str = ""

    @property
    def return_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        raw = (self.exit_price - self.entry_price) / self.entry_price
        if self.side == Side.SELL:
            raw = -raw
        return float(raw)

    @property
    def holding_period(self) -> float:
        return (self.exit_time - self.entry_time).total_seconds()


class OrderUpdate(BaseModel, frozen=True):
    """Status update for a submitted order."""

    order_id: str
    status: OrderStatus
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    message: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
