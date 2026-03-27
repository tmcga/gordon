"""Yahoo Finance data feed powered by the ``yfinance`` library."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime

import pandas as pd
import yfinance as yf

from gordon.core.enums import AssetClass, Interval
from gordon.core.errors import DataError
from gordon.core.models import Asset, Bar
from gordon.data.base import BaseDataFeed

logger = logging.getLogger(__name__)

# Map Gordon intervals to yfinance interval strings.
_INTERVAL_MAP: dict[Interval, str] = {
    Interval.M1: "1m",
    Interval.M5: "5m",
    Interval.M15: "15m",
    Interval.M30: "30m",
    Interval.H1: "1h",
    Interval.H4: "1h",  # yfinance has no native 4h; caller must resample
    Interval.D1: "1d",
    Interval.W1: "1wk",
    Interval.MO1: "1mo",
}


class YFinanceDataFeed(BaseDataFeed):
    """Fetch historical OHLCV bars via Yahoo Finance.

    Supports :pyattr:`AssetClass.EQUITY` and :pyattr:`AssetClass.CRYPTO`.
    For crypto, symbols are converted to yfinance format (e.g. ``BTC`` -> ``BTC-USD``).
    """

    def __init__(self, *, cache_enabled: bool = True) -> None:
        super().__init__(cache_enabled=cache_enabled)

    # ------------------------------------------------------------------
    # Internal fetch
    # ------------------------------------------------------------------

    async def _fetch_bars(
        self,
        asset: Asset,
        interval: Interval,
        start: datetime,
        end: datetime | None,
    ) -> pd.DataFrame:
        yf_symbol = self._to_yf_symbol(asset)
        yf_interval = _INTERVAL_MAP.get(interval)
        if yf_interval is None:
            raise DataError(f"Unsupported interval for yfinance: {interval}")

        logger.info(
            "Fetching %s bars for %s (%s -> %s)",
            yf_interval,
            yf_symbol,
            start.date(),
            end.date() if end else "now",
        )

        loop = asyncio.get_running_loop()
        df: pd.DataFrame = await loop.run_in_executor(
            None,
            lambda: yf.download(
                yf_symbol,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d") if end else None,
                interval=yf_interval,
                progress=False,
                auto_adjust=True,
            ),
        )

        if df.empty:
            raise DataError(f"No data returned by yfinance for {yf_symbol}")

        # yfinance may return MultiIndex columns when single ticker is passed;
        # flatten if necessary.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Rename to lowercase standard
        df.columns = [c.lower().strip() for c in df.columns]
        return df

    # ------------------------------------------------------------------
    # Streaming — not supported
    # ------------------------------------------------------------------

    def subscribe(
        self,
        asset: Asset,
        interval: Interval,
    ) -> AsyncIterator[Bar]:
        raise NotImplementedError(
            "YFinanceDataFeed does not support live streaming. "
            "Use a broker or exchange feed for real-time data."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_yf_symbol(asset: Asset) -> str:
        """Convert a Gordon ``Asset`` to a yfinance ticker string."""
        symbol = asset.symbol.upper()
        if asset.asset_class == AssetClass.CRYPTO:
            # yfinance expects crypto as e.g. "BTC-USD"
            if not symbol.endswith("-USD"):
                symbol = f"{symbol}-USD"
        return symbol
