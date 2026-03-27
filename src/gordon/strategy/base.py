"""Abstract base class for trading strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gordon.core.models import Asset, Bar, PortfolioSnapshot, Signal


class Strategy(ABC):
    """Base class all Gordon strategies inherit from.

    Satisfies ``StrategyProtocol`` while providing lifecycle hooks and a
    parameter bag that concrete strategies can lean on.
    """

    strategy_id: str

    def __init__(
        self,
        strategy_id: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.strategy_id = strategy_id
        self._params = params or {}

    # ------------------------------------------------------------------
    # Core hook — subclasses MUST implement
    # ------------------------------------------------------------------

    @abstractmethod
    def on_bar(
        self,
        asset: Asset,
        bar: Bar,
        portfolio: PortfolioSnapshot,
    ) -> list[Signal]:
        """Called on each new bar. Return zero or more signals."""
        ...

    # ------------------------------------------------------------------
    # Lifecycle hooks — optional overrides
    # ------------------------------------------------------------------

    def on_start(self) -> None:  # noqa: B027
        """Called when the engine starts. Override for initialization."""

    def on_stop(self) -> None:  # noqa: B027
        """Called when the engine stops. Override for cleanup."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def params(self) -> dict[str, Any]:
        return self._params

    def __repr__(self) -> str:
        return f"{type(self).__name__}(strategy_id={self.strategy_id!r})"
