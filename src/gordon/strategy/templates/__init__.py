"""Built-in strategy templates — auto-registered with the default registry."""

from __future__ import annotations

from gordon.strategy.registry import default_registry
from gordon.strategy.templates.mean_reversion import MeanReversion
from gordon.strategy.templates.momentum import Momentum
from gordon.strategy.templates.sma_crossover import SmaCrossover

__all__ = [
    "MeanReversion",
    "Momentum",
    "SmaCrossover",
]

# Auto-register with the default registry
for _cls in (SmaCrossover, Momentum, MeanReversion):
    default_registry.register(_cls)
