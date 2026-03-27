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
    from gordon.core.models import Asset
    from gordon.core.protocols import DataFeedProtocol
    from gordon.persistence.store import TradeStore
    from gordon.risk.manager import RiskManager
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
        risk_manager: RiskManager | None = None,
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
        self._risk_manager = risk_manager
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
        fill_count: int = 0

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
                    bar = await fetch_latest_bar(self._data_feed, asset, self._interval)
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
                    signals = evaluate_strategies(self._strategies, asset, bar, portfolio)

                    # Convert signals to orders and submit
                    for sig in signals:
                        order = signal_to_order(sig, portfolio, close_price, self._risk_manager)
                        if order is None:
                            continue
                        fill = await broker.submit_order(order)
                        if fill is not None:
                            fill_count += 1
                            tracker.on_fill(fill)
                            await bus.emit(FillEvent(timestamp=now, fill=fill))
                            persist_fill(self._store, fill, sig.strategy_id)

                await asyncio.sleep(self._poll_interval)

        finally:
            # Close all open positions
            logger.info("paper_engine_closing_positions")
            closing_fills = await close_positions(broker, tracker, bus)
            fill_count += len(closing_fills)
            for cfill in closing_fills:
                persist_fill(self._store, cfill)

            # Notify strategies
            for strat in self._strategies:
                strat.on_stop()

            # Persist final snapshot
            if self._store is not None:
                snapshot = tracker.snapshot(clock.now())
                self._store.record_snapshot(snapshot)
                for trade in tracker.trade_records:
                    self._store.record_trade(trade)
                self._store.close()

            logger.info(
                "paper_engine_stopped",
                total_fills=fill_count,
                final_equity=str(tracker.total_equity),
            )

    async def stop(self) -> None:
        """Signal the engine to stop gracefully."""
        logger.info("paper_engine_stop_requested")
        self._running = False
