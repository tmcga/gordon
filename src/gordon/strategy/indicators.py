"""Thin wrappers around pandas-ta for common technical indicators.

Every helper accepts a DataFrame whose OHLCV columns contain
``Decimal`` values (the Gordon convention) and transparently converts
to ``float`` before delegating to pandas-ta.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Iterable
import pandas_ta as ta

# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def bars_to_dataframe(bars: Iterable[Any]) -> pd.DataFrame:
    """Convert an iterable of Bar models to an OHLCV DataFrame."""
    return pd.DataFrame(
        [
            {
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]
    )


def _float_series(s: pd.Series) -> pd.Series:
    """Convert a Series of Decimal (or mixed) values to float64."""
    return s.astype(float)


def _ohlcv_floats(
    df: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Return (open, high, low, close, volume) as float64 Series."""
    return (
        _float_series(df["open"]),
        _float_series(df["high"]),
        _float_series(df["low"]),
        _float_series(df["close"]),
        _float_series(df["volume"]),
    )


# ------------------------------------------------------------------
# Moving averages
# ------------------------------------------------------------------


def sma(df: pd.DataFrame, period: int) -> pd.Series:
    """Simple moving average of the *close* price."""
    close = _float_series(df["close"])
    result = ta.sma(close, length=period)
    assert result is not None, f"SMA({period}) returned None"
    return result


def ema(df: pd.DataFrame, period: int) -> pd.Series:
    """Exponential moving average of the *close* price."""
    close = _float_series(df["close"])
    result = ta.ema(close, length=period)
    assert result is not None, f"EMA({period}) returned None"
    return result


# ------------------------------------------------------------------
# Oscillators
# ------------------------------------------------------------------


def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    close = _float_series(df["close"])
    result = ta.rsi(close, length=period)
    assert result is not None, f"RSI({period}) returned None"
    return result


def macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """MACD with columns ``MACD``, ``SIGNAL``, ``HISTOGRAM``."""
    close = _float_series(df["close"])
    raw = ta.macd(close, fast=fast, slow=slow, signal=signal)
    assert raw is not None, "MACD returned None"
    raw.columns = ["MACD", "HISTOGRAM", "SIGNAL"]
    return raw


# ------------------------------------------------------------------
# Volatility
# ------------------------------------------------------------------


def bbands(
    df: pd.DataFrame,
    period: int = 20,
    std: float = 2.0,
) -> pd.DataFrame:
    """Bollinger Bands with columns ``LOWER``, ``MIDDLE``, ``UPPER``."""
    close = _float_series(df["close"])
    raw = ta.bbands(close, length=period, std=std)  # type: ignore[arg-type]
    assert raw is not None, f"BBands({period}) returned None"
    # pandas-ta returns: BBL, BBM, BBU, BBB, BBP
    return pd.DataFrame(
        {
            "LOWER": raw.iloc[:, 0],
            "MIDDLE": raw.iloc[:, 1],
            "UPPER": raw.iloc[:, 2],
        }
    )


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    _, high, low, close, _ = _ohlcv_floats(df)
    result = ta.atr(high=high, low=low, close=close, length=period)
    assert result is not None, f"ATR({period}) returned None"
    return result
