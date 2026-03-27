"""Shared helpers for signal-to-order conversion and position closing.

Extracted from BacktestEngine so PaperEngine and LiveEngine can reuse them
without duplicating logic.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from gordon.core.enums import OrderType, Side
from gordon.core.events import FillEvent
from gordon.core.models import Order

if TYPE_CHECKING:
    from gordon.broker.simulated import SimulatedBroker
    from gordon.core.models import Fill, PortfolioSnapshot, Signal
    from gordon.engine.event_bus import EventBus
    from gordon.portfolio.tracker import PortfolioTracker

logger = structlog.get_logger()

_ENGINE_CLOSE_ID = "__engine_close__"


def signal_to_order(
    signal: Signal,
    portfolio: PortfolioSnapshot,
    price: Decimal,
) -> Order | None:
    """Convert a Signal into an Order using strength-based sizing."""
    if price <= 0:
        return None

    strength = abs(signal.strength)
    if strength < 1e-9:
        return None

    if signal.side == Side.BUY:
        available = portfolio.cash
        notional = available * Decimal(str(strength))
        quantity = (notional / price).quantize(Decimal("0.0001"))
        if quantity <= 0:
            return None
    else:
        # Sell: sell proportion of current holding
        held = Decimal("0")
        for pos in portfolio.positions:
            if pos.asset == signal.asset and pos.quantity > 0:
                held = pos.quantity
                break
        quantity = (held * Decimal(str(strength))).quantize(Decimal("0.0001"))
        if quantity <= 0:
            return None

    return Order(
        asset=signal.asset,
        side=signal.side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        strategy_id=signal.strategy_id,
    )


async def close_positions(
    broker: SimulatedBroker,
    tracker: PortfolioTracker,
    bus: EventBus | None = None,
) -> list[Fill]:
    """Close all open positions at current market prices.

    Submits market orders for every non-zero position and applies fills
    to the tracker.  Optionally emits :class:`FillEvent` on *bus*.
    """
    fills: list[Fill] = []
    positions = list(tracker.positions.values())
    for pos in positions:
        if pos.quantity == Decimal("0"):
            continue
        side = Side.SELL if pos.quantity > 0 else Side.BUY
        order = Order(
            asset=pos.asset,
            side=side,
            order_type=OrderType.MARKET,
            quantity=abs(pos.quantity),
            strategy_id=_ENGINE_CLOSE_ID,
        )
        fill = await broker.submit_order(order)
        if fill is not None:
            fills.append(fill)
            tracker.on_fill(fill)
            if bus is not None:
                await bus.emit(FillEvent(timestamp=fill.timestamp, fill=fill))
    return fills
