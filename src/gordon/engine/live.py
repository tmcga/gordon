"""Live trading engine -- real data with real order execution.

Same polling loop as :class:`PaperEngine` but routes orders through a real
broker that conforms to :class:`~gordon.core.protocols.BrokerProtocol`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from gordon.core.enums import Interval
from gordon.core.events import FillEvent, MarketEvent
from gordon.engine._helpers import (
    close_positions,
    evaluate_strategies,
    fetch_latest_bar,
    persist_fill,
    signal_to_order,
)
from gordon.engine.clock import WallClock
from gordon.engine.event_bus import EventBus
from gordon.portfolio.tracker import PortfolioTracker

if TYPE_CHECKING:
    from gordon.core.models import Asset, Fill, Order
    from gordon.core.protocols import BrokerProtocol, DataFeedProtocol
    from gordon.persistence.store import TradeStore
    from gordon.strategy.base import Strategy

logger = structlog.get_logger()


class LiveEngine:
    """Live market data with real order execution through a broker.

    Same loop as PaperEngine but routes orders through a real broker.
    """

    def __init__(
        self,
        strategies: list[Strategy],
        assets: list[Asset],
        data_feed: DataFeedProtocol,
        broker: BrokerProtocol,
        interval: Interval = Interval.M1,
        initial_cash: Decimal = Decimal("100000"),
        poll_interval: float = 60.0,
        store: TradeStore | None = None,
    ) -> None:
        self._strategies = strategies
        self._assets = assets
        self._data_feed = data_feed
        self._broker = broker
        self._interval = interval
        self._initial_cash = initial_cash
        self._poll_interval = poll_interval
        self._store = store
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the live trading loop until stopped."""
        self._running = True

        bus = EventBus()
        clock = WallClock()
        tracker = PortfolioTracker(initial_cash=self._initial_cash)
        fill_count: int = 0

        logger.info(
            "live_engine_start",
            strategies=len(self._strategies),
            assets=[str(a) for a in self._assets],
            interval=self._interval.value,
            poll_interval=self._poll_interval,
        )

        for strat in self._strategies:
            strat.on_start()

        try:
            while self._running:
                now = clock.now()

                for asset in self._assets:
                    bar = await fetch_latest_bar(self._data_feed, asset, self._interval)
                    if bar is None:
                        continue

                    close_price = bar.close
                    tracker.update_market_price(asset, close_price)

                    await bus.emit(MarketEvent(timestamp=now, bar=bar))

                    portfolio = tracker.snapshot(now)

                    signals = evaluate_strategies(self._strategies, asset, bar, portfolio)

                    for sig in signals:
                        order = signal_to_order(sig, portfolio, close_price)
                        if order is None:
                            continue
                        fill = await self._submit_and_track(order, tracker, bus, now)
                        if fill is not None:
                            fill_count += 1
                            persist_fill(self._store, fill, sig.strategy_id)

                await asyncio.sleep(self._poll_interval)

        finally:
            # Close all open positions via the real broker
            logger.info("live_engine_closing_positions")
            closing_fills = await close_positions(self._broker, tracker, bus)
            fill_count += len(closing_fills)
            for cfill in closing_fills:
                persist_fill(self._store, cfill)

            for strat in self._strategies:
                strat.on_stop()

            if self._store is not None:
                snapshot = tracker.snapshot(clock.now())
                self._store.record_snapshot(snapshot)
                for trade in tracker.trade_records:
                    self._store.record_trade(trade)
                self._store.close()

            logger.info(
                "live_engine_stopped",
                total_fills=fill_count,
                final_equity=str(tracker.total_equity),
            )

    async def stop(self) -> None:
        """Signal the engine to stop gracefully."""
        logger.info("live_engine_stop_requested")
        self._running = False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _submit_and_track(
        self,
        order: Order,
        tracker: PortfolioTracker,
        bus: EventBus,
        now: object,
    ) -> Fill | None:
        """Submit an order to the real broker and track the fill.

        Since ``submit_order`` now returns ``Fill | None`` directly,
        we simply use the return value.
        """
        try:
            fill = await self._broker.submit_order(order)
            if fill is not None:
                tracker.on_fill(fill)
                ts = now if isinstance(now, datetime) else fill.timestamp
                await bus.emit(FillEvent(timestamp=ts, fill=fill))
                return fill
        except Exception:
            logger.exception(
                "order_submit_error",
                order_id=order.id,
                asset=str(order.asset),
            )
        return None
