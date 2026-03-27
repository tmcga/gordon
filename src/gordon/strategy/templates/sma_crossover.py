"""SMA crossover strategy — buy on golden cross, sell on death cross."""

from __future__ import annotations

from collections import deque
from typing import Any

from gordon.core.enums import Side
from gordon.core.models import Asset, Bar, PortfolioSnapshot, Signal
from gordon.strategy.base import Strategy
from gordon.strategy.indicators import bars_to_dataframe, sma


class SmaCrossover(Strategy):
    """Generate signals when a fast SMA crosses a slow SMA.

    Parameters
    ----------
    fast_period : int
        Look-back for the fast moving average (default 10).
    slow_period : int
        Look-back for the slow moving average (default 30).
    """

    def __init__(
        self,
        strategy_id: str = "sma_crossover",
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(strategy_id=strategy_id, params=params)
        self._fast_period: int = self._params.get("fast_period", 10)
        self._slow_period: int = self._params.get("slow_period", 30)
        # Need at least slow_period + 1 bars to detect a crossover
        maxlen = self._slow_period + 10
        self._bars: deque[Bar] = deque(maxlen=maxlen)
        # True when fast > slow on the *previous* bar
        self._was_above: bool | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self._bars.clear()
        self._was_above = None

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

        if len(self._bars) < self._slow_period + 1:
            return []

        df = bars_to_dataframe(self._bars)
        fast = sma(df, self._fast_period)
        slow = sma(df, self._slow_period)

        fast_now = fast.iloc[-1]
        slow_now = slow.iloc[-1]
        is_above = fast_now > slow_now

        signals: list[Signal] = []

        if self._was_above is not None and is_above != self._was_above:
            side = Side.BUY if is_above else Side.SELL
            spread = abs(fast_now - slow_now) / slow_now
            strength = min(float(spread) * 10, 1.0)
            if side == Side.SELL:
                strength = -strength

            signals.append(
                Signal(
                    asset=asset,
                    side=side,
                    strength=strength,
                    strategy_id=self.strategy_id,
                    reason=(
                        f"SMA({self._fast_period}) crossed "
                        f"{'above' if is_above else 'below'} "
                        f"SMA({self._slow_period})"
                    ),
                )
            )

        self._was_above = is_above
        return signals
