"""Paper trading engine -- live data with simulated fills.

Bridges the gap between backtesting and live trading.  Uses real-time data
but fills orders through :class:`SimulatedBroker`.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from gordon.broker.simulated import CommissionModel, SimulatedBroker, SlippageModel
from gordon.core.enums import Interval
from gordon.core.events import FillEvent, MarketEvent
from gordon.engine._helpers import close_positions, signal_to_order
from gordon.engine.clock import WallClock
from gordon.engine.event_bus import EventBus
from gordon.portfolio.tracker import PortfolioTracker

if TYPE_CHECKING:
    from gordon.core.models import Asset, Bar, Fill, Signal
    from gordon.core.protocols import DataFeedProtocol
    from gordon.persistence.store import TradeStore
    from gordon.strategy.base import Strategy

logger = structlog.get_logger()


class PaperEngine:
    """Live market data with simulated order execution.

    Bridges the gap between backtesting and live trading.
    Uses real-time data but fills orders through SimulatedBroker.
    """

    def __init__(
        self,
        strategies: list[Strategy],
        assets: list[Asset],
        data_feed: DataFeedProtocol,
        interval: Interval = Interval.M1,
        initial_cash: Decimal = Decimal("100000"),
        slippage: SlippageModel | None = None,
        commission: CommissionModel | None = None,
        poll_interval: float = 60.0,
        store: TradeStore | None = None,
    ) -> None:
        self._strategies = strategies
        self._assets = assets
        self._data_feed = data_feed
        self._interval = interval
        self._initial_cash = initial_cash
        self._slippage = slippage
        self._commission = commission
        self._poll_interval = poll_interval
        self._store = store
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the paper trading loop until stopped.

        1. Initialise components
        2. Call on_start on all strategies
        3. Loop: poll for new bars, feed to strategies, execute signals
        4. On stop: close positions, call on_stop, persist final state
        """
        self._running = True

        bus = EventBus()
        clock = WallClock()
        broker = SimulatedBroker(
            slippage=self._slippage,
            commission=self._commission,
        )
        tracker = PortfolioTracker(initial_cash=self._initial_cash)
        all_fills: list[Fill] = []

        logger.info(
            "paper_engine_start",
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

                    # Update prices
                    close_price = bar.close
                    broker.set_current_price(asset, close_price)
                    tracker.update_market_price(asset, close_price)

                    # Emit market event
                    await bus.emit(MarketEvent(timestamp=now, bar=bar))

                    # Snapshot for strategy context
                    portfolio = tracker.snapshot(now)

                    # Evaluate strategies
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

                    # Convert signals to orders and submit
                    for sig in signals:
                        order = signal_to_order(sig, portfolio, close_price)
                        if order is None:
                            continue
                        fill = await broker.submit_order(order)
                        if fill is not None:
                            all_fills.append(fill)
                            tracker.on_fill(fill)
                            await bus.emit(FillEvent(timestamp=now, fill=fill))
                            self._persist_fill(fill, sig.strategy_id)

                await asyncio.sleep(self._poll_interval)

        finally:
            # Close all open positions
            logger.info("paper_engine_closing_positions")
            closing_fills = await close_positions(broker, tracker, bus)
            all_fills.extend(closing_fills)
            for cfill in closing_fills:
                self._persist_fill(cfill)

            # Notify strategies
            for strat in self._strategies:
                strat.on_stop()

            # Persist final snapshot
            if self._store is not None:
                snapshot = tracker.snapshot(clock.now())
                self._store.record_snapshot(snapshot)
                for trade in tracker.trade_records:
                    self._store.record_trade(trade)

            logger.info(
                "paper_engine_stopped",
                total_fills=len(all_fills),
                final_equity=str(tracker.total_equity),
            )

    async def stop(self) -> None:
        """Signal the engine to stop gracefully."""
        logger.info("paper_engine_stop_requested")
        self._running = False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

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
