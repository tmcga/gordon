"""Built-in data feed providers."""

from gordon.data.providers.yfinance import YFinanceDataFeed

__all__ = ["CCXTDataFeed", "YFinanceDataFeed"]


def __getattr__(name: str) -> type:
    if name == "CCXTDataFeed":
        from gordon.data.providers.ccxt_provider import CCXTDataFeed

        return CCXTDataFeed
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
