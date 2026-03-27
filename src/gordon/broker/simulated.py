"""Simulated broker for backtesting."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from gordon.core.enums import OrderType, Side
from gordon.core.errors import BrokerError, OrderRejectedError
from gordon.core.models import Fill, Position

_ZERO = Decimal("0")
_ONE = Decimal("1")
_TEN_K = Decimal("10000")

if TYPE_CHECKING:
    from gordon.core.models import Asset, Order

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Slippage models
# ---------------------------------------------------------------------------


class SlippageModel(ABC):
    """Base class for slippage models."""

    @abstractmethod
    def apply(self, price: Decimal, side: Side, quantity: Decimal) -> Decimal: ...


class NoSlippage(SlippageModel):
    """No slippage applied."""

    def apply(self, price: Decimal, side: Side, quantity: Decimal) -> Decimal:
        return price


class FixedSlippage(SlippageModel):
    """Fixed basis-point slippage."""

    def __init__(self, bps: Decimal = Decimal("5")) -> None:
        self._bps = bps

    def apply(self, price: Decimal, side: Side, quantity: Decimal) -> Decimal:
        factor = self._bps / _TEN_K
        if side == Side.BUY:
            return price * (_ONE + factor)
        return price * (_ONE - factor)


class VolumeSlippage(SlippageModel):
    """Slippage proportional to quantity / volume."""

    def __init__(self, impact_factor: Decimal = Decimal("0.1")) -> None:
        self._impact_factor = impact_factor

    def apply(self, price: Decimal, side: Side, quantity: Decimal) -> Decimal:
        # Simple model: impact = impact_factor * quantity * price / 10000
        impact = self._impact_factor * quantity * price / _TEN_K
        if side == Side.BUY:
            return price + impact
        return price - impact


# ---------------------------------------------------------------------------
# Commission models
# ---------------------------------------------------------------------------


class CommissionModel(ABC):
    """Base class for commission models."""

    @abstractmethod
    def calculate(self, price: Decimal, quantity: Decimal) -> Decimal: ...


class NoCommission(CommissionModel):
    """No commission."""

    def calculate(self, price: Decimal, quantity: Decimal) -> Decimal:
        return _ZERO


class PercentCommission(CommissionModel):
    """Commission as a percentage of notional value."""

    def __init__(self, rate: Decimal = Decimal("0.001")) -> None:  # 10bps default
        self._rate = rate

    def calculate(self, price: Decimal, quantity: Decimal) -> Decimal:
        return price * quantity * self._rate


class FixedCommission(CommissionModel):
    """Fixed commission per trade."""

    def __init__(self, amount: Decimal = Decimal("1.0")) -> None:
        self._amount = amount

    def calculate(self, price: Decimal, quantity: Decimal) -> Decimal:
        return self._amount


# ---------------------------------------------------------------------------
# Simulated broker
# ---------------------------------------------------------------------------


class SimulatedBroker:
    """Simulated broker for backtesting.

    Fills orders at current market price + slippage.
    """

    def __init__(
        self,
        slippage: SlippageModel | None = None,
        commission: CommissionModel | None = None,
    ) -> None:
        self._slippage = slippage or NoSlippage()
        self._commission = commission or NoCommission()
        self._current_prices: dict[str, Decimal] = {}
        self._fills: list[Fill] = []
        self._positions: dict[str, Position] = {}  # keyed by symbol

    # -- Price feed --------------------------------------------------------

    def set_current_price(self, asset: Asset, price: Decimal) -> None:
        """Update the latest known price for an asset (called by engine on each bar)."""
        self._current_prices[asset.symbol] = price

    # -- Order management --------------------------------------------------

    async def submit_order(self, order: Order) -> Fill | None:
        """Fill the order at current price + slippage. Returns the Fill or None."""
        if order.quantity <= 0:
            raise OrderRejectedError("Order quantity must be positive", order_id=order.id)

        symbol = order.asset.symbol
        current_price = self._current_prices.get(symbol)
        if current_price is None:
            raise BrokerError(f"No price available for {symbol}")

        if order.order_type == OrderType.MARKET:
            fill_price = self._slippage.apply(current_price, order.side, order.quantity)
        elif order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise OrderRejectedError(
                    "Limit order requires limit_price",
                    order_id=order.id,
                )
            if order.side == Side.BUY and current_price > order.limit_price:
                return None
            if order.side == Side.SELL and current_price < order.limit_price:
                return None
            fill_price = self._slippage.apply(order.limit_price, order.side, order.quantity)
        else:
            raise OrderRejectedError(
                f"Unsupported order type: {order.order_type}",
                order_id=order.id,
            )

        commission = self._commission.calculate(fill_price, order.quantity)

        fill = Fill(
            order_id=order.id,
            asset=order.asset,
            side=order.side,
            price=fill_price,
            quantity=order.quantity,
            commission=commission,
            timestamp=datetime.now(tz=UTC),
        )
        self._fills.append(fill)
        self._update_position(fill)

        logger.info(
            "order_filled",
            order_id=order.id,
            symbol=symbol,
            side=order.side,
            price=str(fill_price),
            quantity=str(order.quantity),
            commission=str(commission),
        )

        return fill

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order. Simulated broker fills immediately, so nothing to cancel."""
        return False

    async def get_positions(self) -> list[Position]:
        """Return current positions."""
        return [p for p in self._positions.values() if p.quantity != _ZERO]

    async def get_fills(self, since: datetime | None = None) -> list[Fill]:
        """Return fills, optionally filtered by timestamp."""
        if since is None:
            return list(self._fills)
        return [f for f in self._fills if f.timestamp >= since]

    @property
    def fill_history(self) -> list[Fill]:
        """All fills that have occurred."""
        return list(self._fills)

    # -- Internal ----------------------------------------------------------

    def _update_position(self, fill: Fill) -> None:
        """Update internal position tracking based on a fill."""
        symbol = fill.asset.symbol
        existing = self._positions.get(symbol)

        if existing is None or existing.quantity == _ZERO:
            # New position
            self._positions[symbol] = Position(
                asset=fill.asset,
                quantity=(fill.quantity if fill.side == Side.BUY else -fill.quantity),
                avg_entry_price=fill.price,
            )
        else:
            old_qty = existing.quantity
            new_qty = old_qty + fill.quantity if fill.side == Side.BUY else old_qty - fill.quantity

            if new_qty == _ZERO:
                # Position fully closed
                self._positions[symbol] = Position(
                    asset=fill.asset,
                    quantity=_ZERO,
                    avg_entry_price=_ZERO,
                )
            elif (old_qty > 0 and new_qty > 0) or (old_qty < 0 and new_qty < 0):
                # Adding to position or partial close on same side
                if abs(new_qty) > abs(old_qty):
                    # Adding to position: recalculate avg price
                    total_cost = (
                        existing.avg_entry_price * abs(old_qty) + fill.price * fill.quantity
                    )
                    avg_price = total_cost / abs(new_qty)
                else:
                    # Partial close: avg entry stays the same
                    avg_price = existing.avg_entry_price
                self._positions[symbol] = Position(
                    asset=fill.asset,
                    quantity=new_qty,
                    avg_entry_price=avg_price,
                )
            else:
                # Flipping sides (e.g. long to short)
                self._positions[symbol] = Position(
                    asset=fill.asset,
                    quantity=new_qty,
                    avg_entry_price=fill.price,
                )
