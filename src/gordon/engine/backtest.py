"""Backtesting engine — replays historical bars through the event pipeline.

Merges OHLCV DataFrames for multiple assets into a single time-ordered stream,
feeds each bar through the strategy layer, converts signals to orders, and
produces a ``BacktestResult`` with equity snapshots and risk metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pandas as pd
import structlog

from gordon.broker.simulated import CommissionModel, SimulatedBroker, SlippageModel
from gordon.core.events import FillEvent, MarketEvent
from gordon.core.models import (
    Asset,
    Bar,
    Fill,
    PortfolioSnapshot,
    Signal,
    TradeRecord,
)
from gordon.engine._helpers import close_positions, signal_to_order
from gordon.engine.clock import SimulatedClock
from gordon.engine.event_bus import EventBus
from gordon.portfolio.tracker import PortfolioTracker
from gordon.risk.metrics import compute_metrics

if TYPE_CHECKING:
    from gordon.risk.manager import RiskManager
    from gordon.strategy.base import Strategy

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class BacktestResult:
    """Results from a completed backtest."""

    start_date: datetime
    end_date: datetime
    initial_cash: Decimal
    final_equity: Decimal
    total_return: float
    trades: list[TradeRecord]
    snapshots: list[PortfolioSnapshot]
    fills: list[Fill]
    metrics: dict[str, float]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass
class _TimedBar:
    """A bar tagged with its asset for merging across instruments."""

    timestamp: datetime
    asset: Asset
    bar: Bar


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BacktestEngine:
    """Replay historical data through strategies and produce results.

    Parameters
    ----------
    strategies:
        One or more ``Strategy`` instances to evaluate on each bar.
    data:
        Mapping of ``Asset`` to a pandas DataFrame with columns
        ``open, high, low, close, volume`` and a ``DatetimeIndex``.
    initial_cash:
        Starting cash balance for the simulated portfolio.
    slippage:
        Optional slippage model applied to every fill.
    commission:
        Optional commission model applied to every fill.
    """

    def __init__(
        self,
        strategies: list[Strategy],
        data: dict[Asset, pd.DataFrame],
        initial_cash: Decimal = Decimal("100000"),
        slippage: SlippageModel | None = None,
        commission: CommissionModel | None = None,
        risk_manager: RiskManager | None = None,
    ) -> None:
        self._strategies = strategies
        self._data = data
        self._initial_cash = initial_cash
        self._slippage = slippage
        self._commission = commission
        self._risk_manager = risk_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> BacktestResult:
        """Execute the backtest and return results."""
        logger.info(
            "backtest_start",
            strategies=len(self._strategies),
            assets=len(self._data),
            initial_cash=str(self._initial_cash),
        )

        # 1. Initialise components
        bus = EventBus()
        clock = SimulatedClock()
        broker = SimulatedBroker(
            slippage=self._slippage,
            commission=self._commission,
        )
        tracker = PortfolioTracker(initial_cash=self._initial_cash)
        snapshots: list[PortfolioSnapshot] = []
        all_fills: list[Fill] = []

        # 2. Merge bars from all assets into a single time-ordered stream
        bars = self._merge_bars()
        if not bars:
            logger.warning("backtest_no_bars")
            return self._empty_result()

        # Notify strategies
        for strat in self._strategies:
            strat.on_start()

        # 3. Process each bar
        for tbar in bars:
            # a. Advance clock
            clock.advance(tbar.timestamp)

            # b. Update broker and tracker prices
            close_price = tbar.bar.close
            broker.set_current_price(tbar.asset, close_price)
            tracker.update_market_price(tbar.asset, close_price)

            # c. Emit MarketEvent
            mkt_event = MarketEvent(
                timestamp=tbar.timestamp,
                bar=tbar.bar,
            )
            await bus.emit(mkt_event)

            # d. Snapshot for strategy context and equity curve
            portfolio = tracker.snapshot(tbar.timestamp)

            # e. Evaluate each strategy
            signals: list[Signal] = []
            for strat in self._strategies:
                try:
                    sigs = strat.on_bar(tbar.asset, tbar.bar, portfolio)
                    signals.extend(sigs)
                except Exception:
                    logger.exception(
                        "strategy_error",
                        strategy=strat.strategy_id,
                        asset=str(tbar.asset),
                    )

            # f. Convert signals to orders and submit
            for sig in signals:
                order = signal_to_order(sig, portfolio, close_price, self._risk_manager)
                if order is None:
                    continue
                fill = await broker.submit_order(order)
                if fill is not None:
                    all_fills.append(fill)
                    tracker.on_fill(fill)
                    await bus.emit(FillEvent(timestamp=tbar.timestamp, fill=fill))

            # g. Record snapshot (post-fill for accurate equity)
            if signals:
                snapshots.append(tracker.snapshot(tbar.timestamp))
            else:
                snapshots.append(portfolio)

        # 4. Close all open positions at final prices
        closing_fills = await close_positions(broker, tracker, bus)
        all_fills.extend(closing_fills)

        # Final snapshot after closing
        if bars:
            final_snap = tracker.snapshot(clock.now())
            snapshots.append(final_snap)

        # Notify strategies
        for strat in self._strategies:
            strat.on_stop()

        # 5. Compute metrics
        trades = tracker.trade_records
        metrics = compute_metrics(snapshots, trades)

        # 6. Build result
        final_equity = snapshots[-1].total_equity if snapshots else self._initial_cash
        total_return = metrics.get("total_return", 0.0)

        result = BacktestResult(
            start_date=bars[0].timestamp,
            end_date=bars[-1].timestamp,
            initial_cash=self._initial_cash,
            final_equity=final_equity,
            total_return=total_return,
            trades=trades,
            snapshots=snapshots,
            fills=all_fills,
            metrics=metrics,
        )

        logger.info(
            "backtest_complete",
            total_return=f"{total_return:.2%}",
            trades=len(trades),
            final_equity=str(final_equity),
        )
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _merge_bars(self) -> list[_TimedBar]:
        """Merge OHLCV DataFrames across assets into time-sorted bars."""
        from gordon.core.enums import Interval

        timed: list[_TimedBar] = []
        for asset, df in self._data.items():
            for ts, row in df.iterrows():
                timestamp = pd.Timestamp(ts).to_pydatetime()  # type: ignore[arg-type]
                bar = Bar(
                    asset=asset,
                    timestamp=timestamp,
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=Decimal(str(row.get("volume", 0))),
                    interval=Interval.D1,
                )
                timed.append(_TimedBar(timestamp=timestamp, asset=asset, bar=bar))

        timed.sort(key=lambda tb: tb.timestamp)
        return timed

    def _empty_result(self) -> BacktestResult:
        """Return a stub result when there is no data."""
        now = datetime.now(tz=UTC)
        return BacktestResult(
            start_date=now,
            end_date=now,
            initial_cash=self._initial_cash,
            final_equity=self._initial_cash,
            total_return=0.0,
            trades=[],
            snapshots=[],
            fills=[],
            metrics={},
        )
