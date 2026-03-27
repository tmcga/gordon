"""Abstract base class for data feeds."""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import pandas as pd

from gordon.core.errors import DataError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import datetime

    from gordon.core.enums import Interval
    from gordon.core.models import Asset, Bar

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


class BaseDataFeed(ABC):
    """Common data-feed logic: caching, normalization, and column validation."""

    def __init__(self, *, cache_enabled: bool = True) -> None:
        self._cache: dict[str, pd.DataFrame] = {}
        self._cache_enabled = cache_enabled

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_bars(
        self,
        asset: Asset,
        interval: Interval,
        start: datetime,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV bars, returning a normalised DataFrame.

        Columns: open, high, low, close, volume (all ``Decimal``).
        Index: ``DatetimeIndex`` named ``timestamp``.
        """
        cache_key = self._cache_key(asset, interval, start, end)
        if self._cache_enabled and cache_key in self._cache:
            logger.debug("Cache hit for %s", cache_key)
            return self._cache[cache_key]

        df = await self._fetch_bars(asset, interval, start, end)
        df = self._normalize(df)

        if self._cache_enabled:
            self._cache[cache_key] = df
        return df

    @abstractmethod
    def subscribe(
        self,
        asset: Asset,
        interval: Interval,
    ) -> AsyncIterator[Bar]:
        """Stream live bars.  Subclasses may raise ``NotImplementedError``."""
        ...  # pragma: no cover

    # ------------------------------------------------------------------
    # Template method for subclasses
    # ------------------------------------------------------------------

    @abstractmethod
    async def _fetch_bars(
        self,
        asset: Asset,
        interval: Interval,
        start: datetime,
        end: datetime | None,
    ) -> pd.DataFrame:
        """Return raw OHLCV data; normalisation is handled by the base class."""
        ...  # pragma: no cover

    # ------------------------------------------------------------------
    # Normalization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
        """Ensure standard column names, Decimal dtype, and DatetimeIndex."""
        if df.empty:
            return df

        # Lowercase column names
        df.columns = [c.lower().strip() for c in df.columns]

        # Validate required columns exist
        missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
        if missing:
            raise DataError(f"Missing columns after fetch: {missing}")

        # Keep only OHLCV columns
        df = df[list(OHLCV_COLUMNS)].copy()

        # Convert to Decimal
        for col in OHLCV_COLUMNS:
            df[col] = df[col].apply(_to_decimal)  # type: ignore[arg-type]

        # Ensure proper index
        if not isinstance(df.index, pd.DatetimeIndex):
            if "timestamp" in df.columns:
                df = df.set_index("timestamp")
            elif "date" in df.columns:
                df = df.set_index("date")
        df.index.name = "timestamp"
        df.index = pd.to_datetime(df.index, utc=True)
        df.sort_index(inplace=True)

        return df

    @staticmethod
    def _cache_key(
        asset: Asset,
        interval: Interval,
        start: datetime,
        end: datetime | None,
    ) -> str:
        raw = f"{asset.symbol}|{asset.asset_class}|{interval}|{start.isoformat()}|{end}"
        return hashlib.md5(raw.encode()).hexdigest()

    def clear_cache(self) -> None:
        """Drop all cached data."""
        self._cache.clear()


def _to_decimal(value: object) -> Decimal:
    """Best-effort conversion to Decimal."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DataError(f"Cannot convert {value!r} to Decimal") from exc
