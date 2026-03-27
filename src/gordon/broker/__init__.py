"""Broker — order execution adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gordon.broker.simulated import (
    CommissionModel,
    FixedCommission,
    FixedSlippage,
    NoCommission,
    NoSlippage,
    PercentCommission,
    SimulatedBroker,
    SlippageModel,
    VolumeSlippage,
)

if TYPE_CHECKING:
    from gordon.broker.alpaca_broker import AlpacaBroker
    from gordon.broker.ccxt_broker import CCXTBroker

__all__ = [
    "AlpacaBroker",
    "CCXTBroker",
    "CommissionModel",
    "FixedCommission",
    "FixedSlippage",
    "NoCommission",
    "NoSlippage",
    "PercentCommission",
    "SimulatedBroker",
    "SlippageModel",
    "VolumeSlippage",
]


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    """Lazy-import broker adapters that have optional dependencies."""
    if name == "CCXTBroker":
        from gordon.broker.ccxt_broker import CCXTBroker

        return CCXTBroker
    if name == "AlpacaBroker":
        from gordon.broker.alpaca_broker import AlpacaBroker

        return AlpacaBroker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
