"""Protocol contracts — structural typing for Gordon's extension points.

Using Protocol (PEP 544) so third-party code can conform without inheriting from Gordon.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import datetime

    import pandas as pd

    from gordon.core.enums import Interval
    from gordon.core.models import (
        Asset,
        Bar,
        Fill,
        Order,
        PortfolioSnapshot,
        Position,
        Signal,
    )

    pass


@runtime_checkable
class DataFeedProtocol(Protocol):
    """Provides market data — historical or live."""

    async def get_bars(
        self,
        asset: Asset,
        interval: Interval,
        start: datetime,
        end: datetime | None = None,
    ) -> pd.DataFrame: ...

    async def subscribe(
        self,
        asset: Asset,
        interval: Interval,
    ) -> AsyncIterator[Bar]: ...


@runtime_checkable
class BrokerProtocol(Protocol):
    """Submits and manages orders."""

    async def submit_order(self, order: Order) -> Fill | None: ...

    async def cancel_order(self, order_id: str) -> bool: ...

    async def get_positions(self) -> list[Position]: ...

    async def get_fills(self, since: datetime | None = None) -> list[Fill]: ...


@runtime_checkable
class StrategyProtocol(Protocol):
    """Generates signals from market data."""

    strategy_id: str

    def on_bar(self, asset: Asset, bar: Bar, portfolio: PortfolioSnapshot) -> list[Signal]: ...


class RiskGuardProtocol(Protocol):
    """Pre-trade check that can approve or reject an order."""

    name: str

    def check(self, order: Order, portfolio: PortfolioSnapshot) -> RiskVerdict: ...


class RiskVerdict:
    """Result of a risk guard check."""

    __slots__ = ("approved", "reason")

    def __init__(self, approved: bool, reason: str = "") -> None:
        self.approved = approved
        self.reason = reason

    def __bool__(self) -> bool:
        return self.approved

    def __repr__(self) -> str:
        status = "APPROVED" if self.approved else "REJECTED"
        return f"RiskVerdict({status}, {self.reason!r})"
