"""Live trading engine -- real data with real order execution.

Same polling loop as :class:`PaperEngine` but routes orders through a real
broker that conforms to :class:`~gordon.core.protocols.BrokerProtocol`.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from gordon.core.enums import Interval
from gordon.core.events import FillEvent, MarketEvent
from gordon.engine._helpers import signal_to_order
from gordon.engine.clock import WallClock
from gordon.engine.event_bus import EventBus
from gordon.portfolio.tracker import PortfolioTracker

if TYPE_CHECKING:
    from gordon.core.models import Asset, Bar, Fill, Order, Signal
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
        all_fills: list[Fill] = []

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
                    bar = await self._fetch_latest_bar(asset)
                    if bar is None:
                        continue

                    close_price = bar.close
                    tracker.update_market_price(asset, close_price)

                    await bus.emit(MarketEvent(timestamp=now, bar=bar))

                    portfolio = tracker.snapshot(now)

                    signals: list[Signal] = []
                    for strat in self._strategies:
                        try:
                            sigs = strat.on_bar(asset, bar, portfolio)
                            signals.extend(sigs)
                        except Exception:
                            logger.exception(
                                "strategy_error",
                                strategy=strat.strategy_id,
                                asset=str(asset),
                            )

                    for sig in signals:
                        order = signal_to_order(sig, portfolio, close_price)
                        if order is None:
                            continue
                        fill = await self._submit_and_track(order, tracker, bus, now)
                        if fill is not None:
                            all_fills.append(fill)
                            self._persist_fill(fill, sig.strategy_id)

                await asyncio.sleep(self._poll_interval)

        finally:
            # Close all open positions via the real broker
            logger.info("live_engine_closing_positions")
            closing_fills = await self._close_positions(tracker, bus)
            all_fills.extend(closing_fills)
            for cfill in closing_fills:
                self._persist_fill(cfill)

            for strat in self._strategies:
                strat.on_stop()

            if self._store is not None:
                snapshot = tracker.snapshot(clock.now())
                self._store.record_snapshot(snapshot)
                for trade in tracker.trade_records:
                    self._store.record_trade(trade)

            logger.info(
                "live_engine_stopped",
                total_fills=len(all_fills),
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

        The :class:`BrokerProtocol` returns an order ID string.
        We then poll ``get_fills`` to retrieve the actual fill.
        """
        from datetime import datetime

        try:
            _order_id = await self._broker.submit_order(order)
            # Retrieve fills produced by the broker for this order
            fills = await self._broker.get_fills(since=None)
            # Find the most recent fill matching our order
            for fill in reversed(fills):
                if fill.order_id == order.id:
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

    async def _close_positions(
        self,
        tracker: PortfolioTracker,
        bus: EventBus,
    ) -> list[Fill]:
        """Close all open positions via the real broker."""
        from gordon.core.enums import OrderType, Side
        from gordon.core.models import Order as OrderModel

        fills: list[Fill] = []
        positions = list(tracker.positions.values())
        for pos in positions:
            if pos.quantity == Decimal("0"):
                continue
            side = Side.SELL if pos.quantity > 0 else Side.BUY
            order = OrderModel(
                asset=pos.asset,
                side=side,
                order_type=OrderType.MARKET,
                quantity=abs(pos.quantity),
                strategy_id="__live_close__",
            )
            fill = await self._submit_and_track(order, tracker, bus, WallClock().now())
            if fill is not None:
                fills.append(fill)
        return fills

    async def _fetch_latest_bar(self, asset: Asset) -> Bar | None:
        """Fetch the most recent bar from the data feed."""
        try:
            df = await self._data_feed.get_bars(
                asset=asset,
                interval=self._interval,
                start=WallClock().now(),
                end=None,
            )
            if df is None or df.empty:
                return None

            from gordon.core.models import Bar as BarModel

            row = df.iloc[-1]
            ts = df.index[-1]
            import pandas as pd

            timestamp = pd.Timestamp(ts).to_pydatetime()
            return BarModel(
                asset=asset,
                timestamp=timestamp,
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row.get("volume", 0))),
                interval=self._interval,
            )
        except Exception:
            logger.exception("data_feed_error", asset=str(asset))
            return None

    def _persist_fill(self, fill: Fill, strategy_id: str = "") -> None:
        """Persist a fill to the store if configured."""
        if self._store is not None:
            try:
                self._store.record_fill(fill, strategy_id)
            except Exception:
                logger.exception("store_error", fill_id=fill.order_id)
