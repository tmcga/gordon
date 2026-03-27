"""CCXT-based data feed for crypto exchanges."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import ccxt
import pandas as pd

from gordon.core.enums import Interval
from gordon.core.errors import DataError
from gordon.data.base import BaseDataFeed

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from gordon.core.models import Asset, Bar

logger = logging.getLogger(__name__)

# Map Gordon intervals to CCXT timeframe strings.
_INTERVAL_MAP: dict[Interval, str] = {
    Interval.M1: "1m",
    Interval.M5: "5m",
    Interval.M15: "15m",
    Interval.M30: "30m",
    Interval.H1: "1h",
    Interval.H4: "4h",
    Interval.D1: "1d",
    Interval.W1: "1w",
    Interval.MO1: "1M",
}


class CCXTDataFeed(BaseDataFeed):
    """Fetch historical OHLCV bars from any CCXT-supported exchange.

    Parameters
    ----------
    exchange:
        Exchange identifier recognised by ``ccxt`` (default ``"binance"``).
    cache_enabled:
        Whether to cache fetched data in memory.
    """

    def __init__(
        self,
        exchange: str = "binance",
        *,
        cache_enabled: bool = True,
    ) -> None:
        super().__init__(cache_enabled=cache_enabled)
        self._exchange_id = exchange
        self._exchange: ccxt.Exchange = self._init_exchange(exchange)

    @staticmethod
    def _init_exchange(exchange_id: str) -> ccxt.Exchange:
        if exchange_id not in ccxt.exchanges:
            raise DataError(
                f"Unknown exchange: {exchange_id}. Valid: {', '.join(ccxt.exchanges[:10])}..."
            )
        exchange_class = getattr(ccxt, exchange_id)
        return exchange_class({"enableRateLimit": True})

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
        timeframe = _INTERVAL_MAP.get(interval)
        if timeframe is None:
            raise DataError(f"Unsupported interval for CCXT: {interval}")

        symbol = self._to_ccxt_symbol(asset)
        since_ms = int(start.replace(tzinfo=UTC).timestamp() * 1000)

        logger.info(
            "Fetching %s bars for %s on %s (since %s)",
            timeframe,
            symbol,
            self._exchange_id,
            start.date(),
        )

        all_ohlcv: list[list[object]] = []
        limit = 1000  # most exchanges cap at 1000 per request
        end_ms = int(end.replace(tzinfo=UTC).timestamp() * 1000) if end else None

        while True:
            ohlcv = self._exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                since=since_ms,
                limit=limit,
            )
            if not ohlcv:
                break

            # If we have an end boundary, filter
            if end_ms is not None:
                ohlcv = [row for row in ohlcv if row[0] <= end_ms]

            all_ohlcv.extend(ohlcv)

            if len(ohlcv) < limit:
                break  # no more pages

            # Advance to just past the last timestamp
            since_ms = ohlcv[-1][0] + 1

            if end_ms is not None and since_ms > end_ms:
                break

        if not all_ohlcv:
            raise DataError(f"No data returned by {self._exchange_id} for {symbol}")

        df = pd.DataFrame(
            all_ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        return df

    # ------------------------------------------------------------------
    # Streaming — placeholder
    # ------------------------------------------------------------------

    def subscribe(
        self,
        asset: Asset,
        interval: Interval,
    ) -> AsyncIterator[Bar]:
        raise NotImplementedError(
            "CCXTDataFeed.subscribe() is not yet implemented. "
            "Use websocket-based feeds for real-time data."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_ccxt_symbol(asset: Asset) -> str:
        """Convert a Gordon ``Asset`` to a CCXT symbol (e.g. ``BTC/USDT``)."""
        symbol = asset.symbol.upper()
        # If already in "BASE/QUOTE" format, return as-is
        if "/" in symbol:
            return symbol
        # Default to USDT quote for bare symbols
        return f"{symbol}/USDT"
