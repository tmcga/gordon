"""RSI momentum strategy — buy on oversold bounce, sell on overbought fade."""

from __future__ import annotations

from collections import deque
from typing import Any

from gordon.core.enums import Side
from gordon.core.models import Asset, Bar, PortfolioSnapshot, Signal
from gordon.strategy.base import Strategy
from gordon.strategy.indicators import bars_to_dataframe, rsi


class Momentum(Strategy):
    """Generate signals based on RSI threshold crossovers.

    Parameters
    ----------
    rsi_period : int
        RSI look-back period (default 14).
    overbought : float
        Upper threshold (default 70).
    oversold : float
        Lower threshold (default 30).
    lookback : int
        Number of bars to retain (default 20).
    """

    def __init__(
        self,
        strategy_id: str = "momentum",
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(strategy_id=strategy_id, params=params)
        self._rsi_period: int = self._params.get("rsi_period", 14)
        self._overbought: float = self._params.get("overbought", 70.0)
        self._oversold: float = self._params.get("oversold", 30.0)
        self._lookback: int = self._params.get("lookback", 20)
        maxlen = max(self._rsi_period + self._lookback, 50)
        self._bars: deque[Bar] = deque(maxlen=maxlen)
        self._prev_rsi: float | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self._bars.clear()
        self._prev_rsi = None

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def on_bar(
        self,
        asset: Asset,
        bar: Bar,
        portfolio: PortfolioSnapshot,
    ) -> list[Signal]:
        self._bars.append(bar)

        # Need enough bars for RSI + 1 for crossover detection
        if len(self._bars) < self._rsi_period + 2:
            return []

        df = bars_to_dataframe(self._bars)
        rsi_series = rsi(df, self._rsi_period)
        current_rsi = float(rsi_series.iloc[-1])

        signals: list[Signal] = []

        if self._prev_rsi is not None:
            # BUY: RSI crosses above oversold from below
            if self._prev_rsi <= self._oversold and current_rsi > self._oversold:
                distance = self._oversold - self._prev_rsi
                strength = min(0.5 + (distance / self._oversold) * 0.5, 1.0)
                signals.append(
                    Signal(
                        asset=asset,
                        side=Side.BUY,
                        strength=strength,
                        strategy_id=self.strategy_id,
                        reason=(
                            f"RSI crossed above oversold ({current_rsi:.1f} > {self._oversold})"
                        ),
                    )
                )

            # SELL: RSI crosses below overbought from above
            if self._prev_rsi >= self._overbought and current_rsi < self._overbought:
                distance = self._prev_rsi - self._overbought
                strength = -min(
                    0.5 + (distance / (100 - self._overbought)) * 0.5,
                    1.0,
                )
                signals.append(
                    Signal(
                        asset=asset,
                        side=Side.SELL,
                        strength=strength,
                        strategy_id=self.strategy_id,
                        reason=(
                            f"RSI crossed below overbought "
                            f"({current_rsi:.1f} < {self._overbought})"
                        ),
                    )
                )

        self._prev_rsi = current_rsi
        return signals
