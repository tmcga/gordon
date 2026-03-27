"""Shared helpers for signal-to-order conversion and position closing.

Extracted from BacktestEngine so PaperEngine and LiveEngine can reuse them
without duplicating logic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from gordon.core.enums import Interval, OrderType, Side
from gordon.core.events import FillEvent
from gordon.core.models import Order

if TYPE_CHECKING:
    from gordon.core.models import Asset, Bar, Fill, PortfolioSnapshot, Signal
    from gordon.core.protocols import DataFeedProtocol
    from gordon.engine.event_bus import EventBus
    from gordon.persistence.store import TradeStore
    from gordon.portfolio.tracker import PortfolioTracker
    from gordon.strategy.base import Strategy

logger = structlog.get_logger()

_ENGINE_CLOSE_ID = "__engine_close__"

_LOOKBACK: dict[Interval, timedelta] = {
    Interval.M1: timedelta(minutes=5),
    Interval.M5: timedelta(minutes=25),
    Interval.M15: timedelta(hours=1),
    Interval.M30: timedelta(hours=2),
    Interval.H1: timedelta(hours=5),
    Interval.H4: timedelta(hours=20),
    Interval.D1: timedelta(days=3),
    Interval.W1: timedelta(weeks=3),
    Interval.MO1: timedelta(days=90),
}


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


async def fetch_latest_bar(
    data_feed: DataFeedProtocol,
    asset: Asset,
    interval: Interval,
) -> Bar | None:
    """Fetch the most recent bar from *data_feed*."""
    try:
        import pandas as pd

        from gordon.core.models import Bar as BarModel

        now = datetime.now(tz=UTC)
        lookback = now - _LOOKBACK.get(interval, timedelta(hours=1))
        df = await data_feed.get_bars(
            asset=asset,
            interval=interval,
            start=lookback,
            end=None,
        )
        if df is None or df.empty:
            return None

        row = df.iloc[-1]
        ts = df.index[-1]
        timestamp = pd.Timestamp(ts).to_pydatetime()
        return BarModel(
            asset=asset,
            timestamp=timestamp,
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=Decimal(str(row.get("volume", 0))),
            interval=interval,
        )
    except Exception:
        logger.exception("data_feed_error", asset=str(asset))
        return None


def persist_fill(store: TradeStore | None, fill: Fill, strategy_id: str = "") -> None:
    """Persist a fill to *store* if configured."""
    if store is not None:
        try:
            store.record_fill(fill, strategy_id)
        except Exception:
            logger.exception("store_error", fill_id=fill.order_id)


def evaluate_strategies(
    strategies: list[Strategy],
    asset: Asset,
    bar: Bar,
    portfolio: PortfolioSnapshot,
) -> list[Signal]:
    """Run every strategy's ``on_bar`` and collect signals."""
    signals: list[Signal] = []
    for strat in strategies:
        try:
            sigs = strat.on_bar(asset, bar, portfolio)
            signals.extend(sigs)
        except Exception:
            logger.exception(
                "strategy_error",
                strategy=strat.strategy_id,
                asset=str(asset),
            )
    return signals


async def close_positions(
    broker: object,
    tracker: PortfolioTracker,
    bus: EventBus | None = None,
) -> list[Fill]:
    """Close all open positions at current market prices.

    Submits market orders for every non-zero position and applies fills
    to the tracker.  Optionally emits :class:`FillEvent` on *bus*.

    *broker* can be any object whose ``submit_order(Order)`` returns
    ``Fill | None`` (e.g. :class:`SimulatedBroker` or a live broker).
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
        fill = await broker.submit_order(order)  # type: ignore[attr-defined]
        if fill is not None:
            fills.append(fill)
            tracker.on_fill(fill)
            if bus is not None:
                await bus.emit(FillEvent(timestamp=fill.timestamp, fill=fill))
    return fills
