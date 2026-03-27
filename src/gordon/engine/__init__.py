"""Engine — event bus, clocks, backtesting, and core execution machinery."""

from gordon.engine.backtest import BacktestEngine, BacktestResult
from gordon.engine.clock import Clock, SimulatedClock, WallClock
from gordon.engine.event_bus import EventBus
from gordon.engine.live import LiveEngine
from gordon.engine.paper import PaperEngine
from gordon.engine.runner import EngineRunner

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "Clock",
    "EngineRunner",
    "EventBus",
    "LiveEngine",
    "PaperEngine",
    "SimulatedClock",
    "WallClock",
]
