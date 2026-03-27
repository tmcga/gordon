"""Mean reversion strategy — Bollinger Bands + RSI confluence."""

from __future__ import annotations

from collections import deque
from typing import Any

from gordon.core.enums import Side
from gordon.core.models import Asset, Bar, PortfolioSnapshot, Signal
from gordon.strategy.base import Strategy
from gordon.strategy.indicators import bars_to_dataframe, bbands, rsi


class MeanReversion(Strategy):
    """Generate signals when price deviates far from the mean.

    A BUY fires when price is below the lower Bollinger Band **and**
    RSI < 30.  A SELL fires when price is above the upper band **and**
    RSI > 70.  Signal strength is inversely proportional to the distance
    from the band (stronger when further away).

    Parameters
    ----------
    bb_period : int
        Bollinger Band look-back (default 20).
    bb_std : float
        Band standard-deviation multiplier (default 2.0).
    rsi_period : int
        RSI look-back period (default 14).
    """

    def __init__(
        self,
        strategy_id: str = "mean_reversion",
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(strategy_id=strategy_id, params=params)
        self._bb_period: int = self._params.get("bb_period", 20)
        self._bb_std: float = self._params.get("bb_std", 2.0)
        self._rsi_period: int = self._params.get("rsi_period", 14)
        self._rsi_oversold: float = self._params.get("rsi_oversold", 30.0)
        self._rsi_overbought: float = self._params.get("rsi_overbought", 70.0)
        maxlen = max(self._bb_period, self._rsi_period) + 20
        self._bars: deque[Bar] = deque(maxlen=maxlen)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self._bars.clear()

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

        min_bars = max(self._bb_period, self._rsi_period) + 2
        if len(self._bars) < min_bars:
            return []

        df = bars_to_dataframe(self._bars)
        bands = bbands(df, period=self._bb_period, std=self._bb_std)
        rsi_series = rsi(df, period=self._rsi_period)

        close = float(bar.close)
        current_rsi = float(rsi_series.iloc[-1])
        lower = float(bands["LOWER"].iloc[-1])
        upper = float(bands["UPPER"].iloc[-1])
        middle = float(bands["MIDDLE"].iloc[-1])

        signals: list[Signal] = []

        # BUY — price below lower band AND RSI oversold
        if close < lower and current_rsi < self._rsi_oversold:
            band_width = middle - lower if middle != lower else 1.0
            distance = lower - close
            strength = min(0.5 + (distance / band_width) * 0.5, 1.0)
            signals.append(
                Signal(
                    asset=asset,
                    side=Side.BUY,
                    strength=strength,
                    strategy_id=self.strategy_id,
                    reason=(
                        f"Price ({close:.2f}) below lower BB ({lower:.2f}), RSI {current_rsi:.1f}"
                    ),
                )
            )

        # SELL — price above upper band AND RSI overbought
        if close > upper and current_rsi > self._rsi_overbought:
            band_width = upper - middle if upper != middle else 1.0
            distance = close - upper
            strength = -min(0.5 + (distance / band_width) * 0.5, 1.0)
            signals.append(
                Signal(
                    asset=asset,
                    side=Side.SELL,
                    strength=strength,
                    strategy_id=self.strategy_id,
                    reason=(
                        f"Price ({close:.2f}) above upper BB ({upper:.2f}), RSI {current_rsi:.1f}"
                    ),
                )
            )

        return signals
