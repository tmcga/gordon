"""Strategy framework — base class, indicators, registry, and templates."""

from __future__ import annotations

from gordon.strategy.base import Strategy
from gordon.strategy.indicators import atr, bbands, ema, macd, rsi, sma
from gordon.strategy.registry import StrategyRegistry, default_registry

__all__ = [
    "Strategy",
    "StrategyRegistry",
    "atr",
    "bbands",
    "default_registry",
    "ema",
    "macd",
    "rsi",
    "sma",
]
