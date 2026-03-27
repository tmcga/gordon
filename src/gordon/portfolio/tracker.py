"""Real-time portfolio tracker."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from gordon.core.enums import Side
from gordon.core.models import (
    Fill,
    PortfolioSnapshot,
    Position,
    TradeRecord,
)

if TYPE_CHECKING:
    from datetime import datetime

    from gordon.core.models import Asset

logger = structlog.get_logger()


class _MutablePosition:
    """Internal mutable position state for tracking."""

    __slots__ = (
        "asset",
        "avg_entry_price",
        "first_entry_time",
        "quantity",
        "realized_pnl",
        "total_commission",
    )

    def __init__(self, asset: Asset) -> None:
        self.asset = asset
        self.quantity = Decimal("0")
        self.avg_entry_price = Decimal("0")
        self.realized_pnl = Decimal("0")
        self.total_commission = Decimal("0")
        self.first_entry_time: datetime | None = None

    def to_position(self, market_price: Decimal | None = None) -> Position:
        """Convert to an immutable Position model."""
        if market_price is not None and self.quantity != Decimal("0"):
            unrealized = (market_price - self.avg_entry_price) * self.quantity
        else:
            unrealized = Decimal("0")
        return Position(
            asset=self.asset,
            quantity=self.quantity,
            avg_entry_price=self.avg_entry_price,
            unrealized_pnl=unrealized,
            realized_pnl=self.realized_pnl,
        )


class PortfolioTracker:
    """Track positions, cash, and P&L through the lifecycle of a trading session."""

    def __init__(self, initial_cash: Decimal) -> None:
        self._cash = initial_cash
        self._positions: dict[str, _MutablePosition] = {}
        self._market_prices: dict[str, Decimal] = {}
        self._trade_records: list[TradeRecord] = []
        self._total_realized_pnl = Decimal("0")

    # -- Fill handling -----------------------------------------------------

    def on_fill(self, fill: Fill) -> None:
        """Update positions and cash based on a fill."""
        symbol = fill.asset.symbol
        pos = self._positions.get(symbol)
        if pos is None:
            pos = _MutablePosition(fill.asset)
            self._positions[symbol] = pos

        notional = fill.price * fill.quantity

        if fill.side == Side.BUY:
            self._cash -= notional + fill.commission
            self._apply_buy(pos, fill)
        else:
            self._cash += notional - fill.commission
            self._apply_sell(pos, fill)

        pos.total_commission += fill.commission

        logger.info(
            "portfolio_fill",
            symbol=symbol,
            side=fill.side,
            quantity=str(fill.quantity),
            price=str(fill.price),
            cash=str(self._cash),
        )

    def _apply_buy(self, pos: _MutablePosition, fill: Fill) -> None:
        """Apply a buy fill to the position."""
        if pos.quantity >= Decimal("0"):
            # Adding to long or opening new long
            total_cost = pos.avg_entry_price * pos.quantity + fill.price * fill.quantity
            pos.quantity += fill.quantity
            if pos.quantity != Decimal("0"):
                pos.avg_entry_price = total_cost / pos.quantity
            if pos.first_entry_time is None:
                pos.first_entry_time = fill.timestamp
        else:
            # Covering a short
            close_qty = min(fill.quantity, abs(pos.quantity))
            pnl = (pos.avg_entry_price - fill.price) * close_qty
            pos.realized_pnl += pnl
            self._total_realized_pnl += pnl

            pos.quantity += fill.quantity

            if pos.quantity == Decimal("0"):
                # Fully closed
                self._record_trade(pos, fill, close_qty, pnl)
                pos.avg_entry_price = Decimal("0")
                pos.first_entry_time = None
            elif pos.quantity > Decimal("0"):
                # Flipped to long
                self._record_trade(pos, fill, close_qty, pnl)
                pos.avg_entry_price = fill.price
                pos.first_entry_time = fill.timestamp
            # Still short: avg entry stays the same

    def _apply_sell(self, pos: _MutablePosition, fill: Fill) -> None:
        """Apply a sell fill to the position."""
        if pos.quantity <= Decimal("0"):
            # Adding to short or opening new short
            total_cost = pos.avg_entry_price * abs(pos.quantity) + fill.price * fill.quantity
            pos.quantity -= fill.quantity
            if pos.quantity != Decimal("0"):
                pos.avg_entry_price = total_cost / abs(pos.quantity)
            if pos.first_entry_time is None:
                pos.first_entry_time = fill.timestamp
        else:
            # Closing a long
            close_qty = min(fill.quantity, pos.quantity)
            pnl = (fill.price - pos.avg_entry_price) * close_qty
            pos.realized_pnl += pnl
            self._total_realized_pnl += pnl

            pos.quantity -= fill.quantity

            if pos.quantity == Decimal("0"):
                # Fully closed
                self._record_trade(pos, fill, close_qty, pnl)
                pos.avg_entry_price = Decimal("0")
                pos.first_entry_time = None
            elif pos.quantity < Decimal("0"):
                # Flipped to short
                self._record_trade(pos, fill, close_qty, pnl)
                pos.avg_entry_price = fill.price
                pos.first_entry_time = fill.timestamp
            # Still long: avg entry stays the same

    def _record_trade(
        self,
        pos: _MutablePosition,
        fill: Fill,
        quantity: Decimal,
        pnl: Decimal,
    ) -> None:
        """Record a completed round-trip trade."""
        entry_side = Side.BUY if fill.side == Side.SELL else Side.SELL
        record = TradeRecord(
            asset=pos.asset,
            side=entry_side,
            entry_price=pos.avg_entry_price,
            exit_price=fill.price,
            quantity=quantity,
            entry_time=pos.first_entry_time or fill.timestamp,
            exit_time=fill.timestamp,
            pnl=pnl,
            commission=pos.total_commission,
        )
        self._trade_records.append(record)
        logger.info(
            "trade_closed",
            symbol=pos.asset.symbol,
            pnl=str(pnl),
            entry=str(pos.avg_entry_price),
            exit=str(fill.price),
        )

    # -- Market price updates ----------------------------------------------

    def update_market_price(self, asset: Asset, price: Decimal) -> None:
        """Update unrealized P&L for an asset."""
        self._market_prices[asset.symbol] = price

    # -- Snapshots ---------------------------------------------------------

    def snapshot(self, timestamp: datetime) -> PortfolioSnapshot:
        """Create a point-in-time snapshot of portfolio state."""
        positions = tuple(self.positions.values())
        return PortfolioSnapshot(
            timestamp=timestamp,
            cash=self._cash,
            positions=positions,
            total_equity=self.total_equity,
            unrealized_pnl=self.unrealized_pnl,
            realized_pnl=self.realized_pnl,
        )

    # -- Properties --------------------------------------------------------

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def positions(self) -> dict[str, Position]:
        """Current positions keyed by symbol."""
        result: dict[str, Position] = {}
        for symbol, pos in self._positions.items():
            if pos.quantity != Decimal("0"):
                market_price = self._market_prices.get(symbol)
                result[symbol] = pos.to_position(market_price)
        return result

    @property
    def total_equity(self) -> Decimal:
        """Cash + sum of position market values."""
        equity = self._cash
        for symbol, pos in self._positions.items():
            if pos.quantity == Decimal("0"):
                continue
            market_price = self._market_prices.get(symbol)
            if market_price is not None:
                equity += market_price * pos.quantity
            else:
                equity += pos.avg_entry_price * pos.quantity
        return equity

    @property
    def realized_pnl(self) -> Decimal:
        return self._total_realized_pnl

    @property
    def unrealized_pnl(self) -> Decimal:
        total = Decimal("0")
        for symbol, pos in self._positions.items():
            if pos.quantity == Decimal("0"):
                continue
            market_price = self._market_prices.get(symbol)
            if market_price is not None:
                total += (market_price - pos.avg_entry_price) * pos.quantity
        return total

    @property
    def trade_records(self) -> list[TradeRecord]:
        return list(self._trade_records)
