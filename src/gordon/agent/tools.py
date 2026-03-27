"""AI agent tool definitions and dispatch for the Gordon trading agent.

Each tool is a dict matching the Anthropic ``tool_use`` schema.  The
``execute_tool`` coroutine dispatches incoming tool calls to the
appropriate handler and returns a JSON string result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from gordon.core.enums import AssetClass, Interval, OrderType, Side
from gordon.core.models import Asset, Order
from gordon.risk.metrics import compute_metrics
from gordon.strategy.indicators import atr, bbands, ema, macd, rsi, sma
from gordon.strategy.registry import default_registry

if TYPE_CHECKING:
    from gordon.broker.simulated import SimulatedBroker
    from gordon.data.base import BaseDataFeed
    from gordon.portfolio.tracker import PortfolioTracker
    from gordon.strategy.base import Strategy

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Shared agent context
# ---------------------------------------------------------------------------


@dataclass
class AgentContext:
    """Shared state passed to every tool handler."""

    tracker: PortfolioTracker
    data_feed: BaseDataFeed
    broker: SimulatedBroker | None = None
    strategies: dict[str, Strategy] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# JSON helper
# ---------------------------------------------------------------------------


def _json(obj: Any) -> str:
    """Serialize *obj* to a JSON string suitable for Claude tool output."""
    return json.dumps(obj, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool definitions (Anthropic tool_use schema)
# ---------------------------------------------------------------------------

GET_PORTFOLIO_STATUS: dict[str, Any] = {
    "name": "get_portfolio_status",
    "description": (
        "Return current portfolio state including positions, cash balance, "
        "total equity, and unrealized P&L."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

GET_MARKET_DATA: dict[str, Any] = {
    "name": "get_market_data",
    "description": ("Fetch recent OHLCV bars for a symbol from the configured data feed."),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Ticker symbol, e.g. 'AAPL' or 'BTC'.",
            },
            "interval": {
                "type": "string",
                "description": (
                    "Bar interval. One of: 1m, 5m, 15m, 30m, 1h, 4h, "
                    "1d, 1w, 1mo. Defaults to '1d'."
                ),
                "default": "1d",
            },
            "lookback_days": {
                "type": "integer",
                "description": "Number of calendar days of history to fetch. Default 30.",
                "default": 30,
            },
        },
        "required": ["symbol"],
    },
}

ANALYZE_TECHNICAL: dict[str, Any] = {
    "name": "analyze_technical",
    "description": (
        "Run one or more technical indicators on recent data for a symbol. "
        "Returns the latest indicator values."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Ticker symbol.",
            },
            "indicators": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of indicators to compute. Supported: sma, ema, rsi, macd, bbands, atr."
                ),
            },
        },
        "required": ["symbol", "indicators"],
    },
}

RUN_BACKTEST: dict[str, Any] = {
    "name": "run_backtest",
    "description": (
        "Backtest a registered strategy on the given symbols and date range. "
        "Returns performance metrics and trade summary."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "strategy": {
                "type": "string",
                "description": "Strategy name from the registry (e.g. 'sma_crossover').",
            },
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of ticker symbols to include.",
            },
            "start": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format.",
            },
            "end": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format.",
            },
        },
        "required": ["strategy", "symbols", "start", "end"],
    },
}

SUBMIT_ORDER: dict[str, Any] = {
    "name": "submit_order",
    "description": (
        "Place a trade order through the broker. Returns the fill "
        "confirmation or rejection details."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Ticker symbol to trade.",
            },
            "side": {
                "type": "string",
                "enum": ["buy", "sell"],
                "description": "Order side: 'buy' or 'sell'.",
            },
            "quantity": {
                "type": "number",
                "description": "Number of shares/units to trade.",
            },
            "order_type": {
                "type": "string",
                "enum": ["market", "limit"],
                "description": "Order type. Defaults to 'market'.",
                "default": "market",
            },
        },
        "required": ["symbol", "side", "quantity"],
    },
}

GET_RISK_REPORT: dict[str, Any] = {
    "name": "get_risk_report",
    "description": (
        "Compute current risk and performance metrics from portfolio "
        "snapshots and completed trades."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

LIST_STRATEGIES: dict[str, Any] = {
    "name": "list_strategies",
    "description": "List all registered trading strategies available for backtesting.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

TOOLS: list[dict[str, Any]] = [
    GET_PORTFOLIO_STATUS,
    GET_MARKET_DATA,
    ANALYZE_TECHNICAL,
    RUN_BACKTEST,
    SUBMIT_ORDER,
    GET_RISK_REPORT,
    LIST_STRATEGIES,
]

# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def _handle_get_portfolio_status(ctx: AgentContext) -> str:
    now = datetime.now(tz=UTC)
    positions = ctx.tracker.positions
    pos_list = [
        {
            "symbol": sym,
            "quantity": str(pos.quantity),
            "avg_entry_price": str(pos.avg_entry_price),
            "unrealized_pnl": str(pos.unrealized_pnl),
            "market_value": str(pos.market_value),
        }
        for sym, pos in positions.items()
    ]
    return _json(
        {
            "timestamp": now.isoformat(),
            "cash": str(ctx.tracker.cash),
            "total_equity": str(ctx.tracker.total_equity),
            "unrealized_pnl": str(ctx.tracker.unrealized_pnl),
            "realized_pnl": str(ctx.tracker.realized_pnl),
            "positions": pos_list,
            "position_count": len(pos_list),
        }
    )


async def _handle_get_market_data(
    ctx: AgentContext,
    args: dict[str, Any],
) -> str:
    symbol: str = args["symbol"]
    interval_str: str = args.get("interval", "1d")
    lookback_days: int = args.get("lookback_days", 30)

    asset = Asset(symbol=symbol.upper(), asset_class=AssetClass.EQUITY)
    interval = Interval(interval_str)
    end = datetime.now(tz=UTC)
    start = end - timedelta(days=lookback_days)

    logger.info("get_market_data", symbol=symbol, interval=interval_str, days=lookback_days)
    df = await ctx.data_feed.get_bars(asset, interval, start, end)

    # Return the last 20 bars as a digestible summary
    tail = df.tail(20)
    bars = []
    for ts, row in tail.iterrows():
        bars.append(
            {
                "timestamp": str(ts),
                "open": str(row["open"]),
                "high": str(row["high"]),
                "low": str(row["low"]),
                "close": str(row["close"]),
                "volume": str(row["volume"]),
            }
        )
    return _json(
        {
            "symbol": symbol.upper(),
            "interval": interval_str,
            "total_bars": len(df),
            "bars_returned": len(bars),
            "bars": bars,
        }
    )


_INDICATOR_RUNNERS = {
    "sma": lambda df: {"sma_20": sma(df, 20).dropna().iloc[-1]},
    "ema": lambda df: {"ema_12": ema(df, 12).dropna().iloc[-1]},
    "rsi": lambda df: {"rsi_14": rsi(df, 14).dropna().iloc[-1]},
    "macd": lambda df: {k: v for k, v in macd(df).dropna().iloc[-1].to_dict().items()},
    "bbands": lambda df: {k: v for k, v in bbands(df).dropna().iloc[-1].to_dict().items()},
    "atr": lambda df: {"atr_14": atr(df, 14).dropna().iloc[-1]},
}


async def _handle_analyze_technical(
    ctx: AgentContext,
    args: dict[str, Any],
) -> str:
    symbol: str = args["symbol"]
    indicators: list[str] = args["indicators"]

    asset = Asset(symbol=symbol.upper(), asset_class=AssetClass.EQUITY)
    end = datetime.now(tz=UTC)
    start = end - timedelta(days=90)

    df = await ctx.data_feed.get_bars(asset, Interval.D1, start, end)

    results: dict[str, Any] = {"symbol": symbol.upper()}
    for ind in indicators:
        key = ind.lower()
        runner = _INDICATOR_RUNNERS.get(key)
        if runner is None:
            results[key] = {"error": f"Unknown indicator: {ind}"}
            continue
        try:
            results[key] = runner(df)  # type: ignore[no-untyped-call]
        except Exception as exc:
            logger.warning("indicator_error", indicator=key, error=str(exc))
            results[key] = {"error": str(exc)}

    return _json(results)


async def _handle_run_backtest(
    ctx: AgentContext,
    args: dict[str, Any],
) -> str:
    from gordon.engine.backtest import BacktestEngine

    strategy_name: str = args["strategy"]
    symbols: list[str] = args["symbols"]
    start_str: str = args["start"]
    end_str: str = args["end"]

    start = datetime.fromisoformat(start_str).replace(tzinfo=UTC)
    end = datetime.fromisoformat(end_str).replace(tzinfo=UTC)

    # Resolve strategy
    strategy = default_registry.get(strategy_name)

    # Fetch data for each symbol
    data: dict[Asset, Any] = {}
    for sym in symbols:
        asset = Asset(symbol=sym.upper(), asset_class=AssetClass.EQUITY)
        df = await ctx.data_feed.get_bars(asset, Interval.D1, start, end)
        data[asset] = df

    engine = BacktestEngine(
        strategies=[strategy],
        data=data,
        initial_cash=ctx.tracker.cash,
    )
    result = await engine.run()

    return _json(
        {
            "strategy": strategy_name,
            "symbols": symbols,
            "start": start_str,
            "end": end_str,
            "initial_cash": str(result.initial_cash),
            "final_equity": str(result.final_equity),
            "total_return": f"{result.total_return:.4f}",
            "total_trades": len(result.trades),
            "metrics": result.metrics,
        }
    )


async def _handle_submit_order(
    ctx: AgentContext,
    args: dict[str, Any],
) -> str:
    if ctx.broker is None:
        return _json({"error": "No broker configured. Cannot submit orders."})

    symbol: str = args["symbol"]
    side = Side(args["side"])
    quantity = Decimal(str(args["quantity"]))
    order_type = OrderType(args.get("order_type", "market"))

    asset = Asset(symbol=symbol.upper(), asset_class=AssetClass.EQUITY)
    order = Order(
        asset=asset,
        side=side,
        order_type=order_type,
        quantity=quantity,
        strategy_id="agent",
    )

    logger.info(
        "submit_order",
        symbol=symbol,
        side=side,
        quantity=str(quantity),
        order_type=order_type,
    )

    try:
        fill = await ctx.broker.submit_order(order)
    except Exception as exc:
        logger.warning("order_failed", error=str(exc))
        return _json({"error": str(exc), "order_id": order.id})

    if fill is None:
        return _json(
            {
                "status": "not_filled",
                "order_id": order.id,
                "reason": "Order conditions not met at current price.",
            }
        )

    # Update portfolio tracker
    ctx.tracker.on_fill(fill)

    return _json(
        {
            "status": "filled",
            "order_id": order.id,
            "symbol": symbol.upper(),
            "side": str(fill.side),
            "quantity": str(fill.quantity),
            "fill_price": str(fill.price),
            "commission": str(fill.commission),
            "timestamp": fill.timestamp.isoformat(),
        }
    )


async def _handle_get_risk_report(ctx: AgentContext) -> str:
    now = datetime.now(tz=UTC)
    snapshot = ctx.tracker.snapshot(now)
    trades = ctx.tracker.trade_records
    metrics = compute_metrics([snapshot], trades)

    return _json(
        {
            "timestamp": now.isoformat(),
            "total_equity": str(snapshot.total_equity),
            "cash": str(snapshot.cash),
            "unrealized_pnl": str(snapshot.unrealized_pnl),
            "realized_pnl": str(snapshot.realized_pnl),
            "total_trades": len(trades),
            "metrics": metrics,
        }
    )


async def _handle_list_strategies() -> str:
    names = default_registry.list_strategies()
    return _json({"strategies": names, "count": len(names)})


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Any] = {
    "get_portfolio_status": _handle_get_portfolio_status,
    "get_market_data": _handle_get_market_data,
    "analyze_technical": _handle_analyze_technical,
    "run_backtest": _handle_run_backtest,
    "submit_order": _handle_submit_order,
    "get_risk_report": _handle_get_risk_report,
    "list_strategies": _handle_list_strategies,
}


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    context: AgentContext,
) -> str:
    """Execute a tool call and return the result as a string."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return _json({"error": f"Unknown tool: {name}"})

    logger.info("execute_tool", tool=name, arguments=arguments)

    try:
        # Handlers that take no args beyond context
        if name in ("get_portfolio_status", "get_risk_report"):
            return str(await handler(context))
        if name == "list_strategies":
            return str(await handler())
        return str(await handler(context, arguments))
    except Exception as exc:
        logger.exception("tool_error", tool=name, error=str(exc))
        return _json({"error": str(exc), "tool": name})
