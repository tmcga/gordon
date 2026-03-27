"""Live data feed — polling-based real-time bar streaming."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

import pandas as pd

from gordon.core.enums import Interval
from gordon.core.models import Asset, Bar

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from gordon.data.base import BaseDataFeed

logger = structlog.get_logger()

# Minimum interval between polls to avoid hammering the provider.
_MIN_POLL_SECONDS = 5.0


class LiveDataFeed:
    """Live market data via polling.

    Wraps an existing :class:`BaseDataFeed` provider and yields
    :class:`Bar` objects as they become available. Uses simple polling
    against the provider; can be extended with WebSocket support later.
    """

    def __init__(
        self,
        provider: BaseDataFeed,
        poll_interval: float = 60.0,
    ) -> None:
        self._provider = provider
        self._poll_interval = max(poll_interval, _MIN_POLL_SECONDS)
        self._running = False

    async def stream(
        self,
        asset: Asset,
        interval: Interval,
    ) -> AsyncIterator[Bar]:
        """Yield bars as they become available.

        Polls the underlying provider for recent bars and yields only
        those with a timestamp newer than the last seen bar.
        """
        self._running = True
        last_ts: datetime | None = None

        logger.info(
            "Starting live feed for %s (%s) — poll every %.1fs",
            asset.symbol,
            interval.value,
            self._poll_interval,
        )

        while self._running:
            try:
                now = datetime.now(tz=UTC)
                # Fetch a small window of recent bars.
                lookback = self._lookback_start(now, interval)
                df = await self._provider.get_bars(asset, interval, start=lookback, end=now)

                if df.empty:
                    await asyncio.sleep(self._poll_interval)
                    continue

                for ts, row in df.iterrows():
                    bar_ts = pd.Timestamp(ts).to_pydatetime()  # type: ignore[arg-type]
                    if last_ts is not None and bar_ts <= last_ts:
                        continue

                    bar = Bar(
                        asset=asset,
                        timestamp=bar_ts,
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                        interval=interval,
                    )
                    last_ts = bar_ts
                    yield bar

            except Exception:
                logger.exception(
                    "Error polling %s — retrying in %.1fs",
                    asset.symbol,
                    self._poll_interval,
                )

            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        """Signal the feed to stop streaming."""
        self._running = False
        logger.info("Live feed stop requested")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _lookback_start(now: datetime, interval: Interval) -> datetime:
        """Compute how far back to fetch so we capture the latest bar."""
        from datetime import timedelta

        multipliers: dict[Interval, timedelta] = {
            Interval.M1: timedelta(minutes=5),
            Interval.M5: timedelta(minutes=25),
            Interval.M15: timedelta(hours=1),
            Interval.M30: timedelta(hours=2),
            Interval.H1: timedelta(hours=5),
            Interval.H4: timedelta(hours=20),
            Interval.D1: timedelta(days=3),
            Interval.W1: timedelta(weeks=3),
            Interval.MO1: timedelta(days=90),
        }
        delta = multipliers.get(interval, timedelta(hours=1))
        return now - delta
