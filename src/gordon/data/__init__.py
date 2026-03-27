"""Data module — feeds, providers, and storage."""

from gordon.data.base import BaseDataFeed
from gordon.data.providers.yfinance import YFinanceDataFeed
from gordon.data.storage import load_bars, save_bars

__all__ = [
    "BaseDataFeed",
    "CCXTDataFeed",
    "YFinanceDataFeed",
    "load_bars",
    "save_bars",
]


def __getattr__(name: str) -> type:
    if name == "CCXTDataFeed":
        from gordon.data.providers.ccxt_provider import CCXTDataFeed

        return CCXTDataFeed
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
