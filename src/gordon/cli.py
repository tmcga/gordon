"""Gordon CLI — the command-line interface for the trading agent."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich import print as rprint

import gordon
from gordon.core.enums import AssetClass, Interval
from gordon.core.models import Asset

app = typer.Typer(
    name="gordon",
    help="Gordon — AI-powered trading agent.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

data_app = typer.Typer(help="Market data operations.", no_args_is_help=True)
app.add_typer(data_app, name="data")


# ------------------------------------------------------------------
# Version callback
# ------------------------------------------------------------------


def _version_callback(value: bool) -> None:
    if value:
        rprint(f"gordon {gordon.__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Gordon — AI-powered trading agent."""


# ------------------------------------------------------------------
# data fetch
# ------------------------------------------------------------------


@data_app.command("fetch")
def data_fetch(
    symbol: Annotated[str, typer.Argument(help="Ticker symbol.")],
    start: Annotated[str, typer.Option("--start", "-s", help="Start date.")],
    end: Annotated[str | None, typer.Option("--end", "-e", help="End date.")] = None,
    interval: Annotated[str, typer.Option("--interval", "-i", help="Bar interval.")] = "1d",
    provider: Annotated[str, typer.Option("--provider", "-p", help="Data provider.")] = "yfinance",
    asset_class: Annotated[
        str, typer.Option("--asset-class", "-a", help="Asset class.")
    ] = "equity",
    exchange: Annotated[str | None, typer.Option("--exchange", help="Exchange (CCXT).")] = None,
    output: Annotated[str | None, typer.Option("--output", "-o", help="Output path.")] = None,
) -> None:
    """Fetch historical OHLCV bars and save to Parquet."""
    from gordon.data.providers import CCXTDataFeed, YFinanceDataFeed
    from gordon.data.storage import save_bars

    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d") if end else None

    ac = AssetClass(asset_class)
    asset = Asset(symbol=symbol, asset_class=ac, exchange=exchange)
    iv = Interval(interval)

    if provider == "yfinance":
        feed = YFinanceDataFeed()
    elif provider == "ccxt":
        feed = CCXTDataFeed(exchange=exchange or "binance")
    else:
        rprint(f"[red]Unknown provider:[/red] {provider}")
        raise typer.Exit(code=1)

    rprint(
        f"[bold]Fetching[/bold] {symbol} ({ac}) — "
        f"{iv} bars from {start} to {end or 'now'} via {provider}"
    )

    df = asyncio.run(feed.get_bars(asset, iv, start_dt, end_dt))

    out_path = Path(output) if output else Path("data") / f"{symbol.upper()}_{iv}.parquet"

    save_bars(df, out_path)
    rprint(f"[green]Saved {len(df)} bars to {out_path}[/green]")


# ------------------------------------------------------------------
# Placeholder commands
# ------------------------------------------------------------------


@app.command()
def backtest(
    strategy: Annotated[
        str, typer.Option("--strategy", "-S", help="Strategy name.")
    ] = "sma_crossover",
    symbols: Annotated[str, typer.Option("--symbols", help="Comma-separated symbols.")] = "AAPL",
    start: Annotated[str, typer.Option("--start", "-s", help="Start date.")] = "2023-01-01",
    end: Annotated[str | None, typer.Option("--end", "-e", help="End date.")] = None,
    cash: Annotated[float, typer.Option("--cash", help="Initial cash.")] = 100_000.0,
    provider: Annotated[str, typer.Option("--provider", "-p", help="Data provider.")] = "yfinance",
    asset_class: Annotated[
        str, typer.Option("--asset-class", "-a", help="Asset class.")
    ] = "equity",
) -> None:
    """Run a backtest against historical data."""
    from decimal import Decimal

    from rich.console import Console
    from rich.table import Table

    # Auto-register built-in templates
    import gordon.strategy.templates  # noqa: F401
    from gordon.data.providers import YFinanceDataFeed
    from gordon.engine.backtest import BacktestEngine
    from gordon.strategy.registry import default_registry

    console = Console()

    strat = default_registry.get(strategy)
    if strat is None:
        rprint(f"[red]Unknown strategy:[/red] {strategy}")
        rprint(f"Available: {', '.join(default_registry.list_strategies())}")
        raise typer.Exit(code=1)

    ac = AssetClass(asset_class)
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d") if end else None

    feed = YFinanceDataFeed()
    data: dict[Asset, object] = {}
    symbol_list = [s.strip() for s in symbols.split(",")]

    with console.status("[bold]Fetching market data..."):
        for sym in symbol_list:
            asset = Asset(symbol=sym, asset_class=ac)
            df = asyncio.run(feed.get_bars(asset, Interval.D1, start_dt, end_dt))
            data[asset] = df

    engine = BacktestEngine(
        strategies=[strat],
        data=data,  # type: ignore[arg-type]
        initial_cash=Decimal(str(cash)),
    )

    with console.status("[bold]Running backtest..."):
        result = asyncio.run(engine.run())

    # Display results
    console.print()
    title = (
        f"[bold]Backtest: {strategy}[/bold] | "
        f"{', '.join(symbol_list)} | "
        f"{result.start_date:%Y-%m-%d} to {result.end_date:%Y-%m-%d}"
    )
    console.print(title)
    console.print()

    # Metrics table
    metrics_table = Table(title="Performance Metrics", show_lines=True)
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", style="bold")

    m = result.metrics
    metrics_table.add_row("Initial Cash", f"${cash:,.2f}")
    metrics_table.add_row("Final Equity", f"${result.final_equity:,.2f}")
    metrics_table.add_row("Total Return", f"{m.get('total_return', 0):.2%}")
    metrics_table.add_row("Annualized Return", f"{m.get('annualized_return', 0):.2%}")
    metrics_table.add_row("Sharpe Ratio", f"{m.get('sharpe_ratio', 0):.3f}")
    metrics_table.add_row("Sortino Ratio", f"{m.get('sortino_ratio', 0):.3f}")
    metrics_table.add_row("Max Drawdown", f"{m.get('max_drawdown', 0):.2%}")
    metrics_table.add_row("Calmar Ratio", f"{m.get('calmar_ratio', 0):.3f}")
    metrics_table.add_row("Win Rate", f"{m.get('win_rate', 0):.1%}")
    metrics_table.add_row("Profit Factor", f"{m.get('profit_factor', 0):.2f}")
    metrics_table.add_row("Total Trades", f"{m.get('total_trades', 0):.0f}")

    console.print(metrics_table)

    # Trade log (last 10)
    if result.trades:
        console.print()
        trades_table = Table(title="Recent Trades (last 10)")
        trades_table.add_column("Asset")
        trades_table.add_column("Side")
        trades_table.add_column("Entry")
        trades_table.add_column("Exit")
        trades_table.add_column("Qty")
        trades_table.add_column("P&L", style="bold")

        for trade in result.trades[-10:]:
            pnl_style = "green" if trade.pnl > 0 else "red"
            trades_table.add_row(
                str(trade.asset),
                trade.side.value,
                f"${trade.entry_price:.2f}",
                f"${trade.exit_price:.2f}",
                f"{trade.quantity:.4f}",
                f"[{pnl_style}]${trade.pnl:,.2f}[/{pnl_style}]",
            )
        console.print(trades_table)


@app.command()
def paper(
    strategy: Annotated[
        str, typer.Option("--strategy", "-S", help="Strategy name.")
    ] = "sma_crossover",
    symbols: Annotated[str, typer.Option("--symbols", help="Comma-separated symbols.")] = "AAPL",
    interval: Annotated[str, typer.Option("--interval", "-i", help="Bar interval.")] = "1d",
    cash: Annotated[float, typer.Option("--cash", help="Initial cash.")] = 100_000.0,
    provider: Annotated[str, typer.Option("--provider", "-p", help="Data provider.")] = "yfinance",
    asset_class: Annotated[
        str, typer.Option("--asset-class", "-a", help="Asset class.")
    ] = "equity",
    poll: Annotated[float, typer.Option("--poll", help="Poll interval (seconds).")] = 60.0,
    db: Annotated[
        str, typer.Option("--db", help="SQLite database URL.")
    ] = "sqlite:///gordon_trades.db",
) -> None:
    """Run a paper-trading session with live data and simulated fills."""
    from decimal import Decimal

    import gordon.strategy.templates  # noqa: F401
    from gordon.data.providers import YFinanceDataFeed
    from gordon.engine.paper import PaperEngine
    from gordon.engine.runner import EngineRunner
    from gordon.persistence import TradeStore
    from gordon.strategy.registry import default_registry

    strat = default_registry.get(strategy)
    if strat is None:
        rprint(f"[red]Unknown strategy:[/red] {strategy}")
        raise typer.Exit(code=1)

    ac = AssetClass(asset_class)
    assets = [Asset(symbol=s.strip(), asset_class=ac) for s in symbols.split(",")]
    iv = Interval(interval)
    feed = YFinanceDataFeed()
    store = TradeStore(db_url=db)

    engine = PaperEngine(
        strategies=[strat],
        assets=assets,
        data_feed=feed,  # type: ignore[arg-type]
        interval=iv,
        initial_cash=Decimal(str(cash)),
        poll_interval=poll,
        store=store,
    )

    rprint(f"[bold]Paper trading[/bold] {strategy} on {symbols} ({iv}) — Ctrl+C to stop")
    runner = EngineRunner(engine)
    runner.run()


@app.command()
def live(
    strategy: Annotated[
        str, typer.Option("--strategy", "-S", help="Strategy name.")
    ] = "sma_crossover",
    symbols: Annotated[
        str, typer.Option("--symbols", help="Comma-separated symbols.")
    ] = "BTC/USDT",
    interval: Annotated[str, typer.Option("--interval", "-i", help="Bar interval.")] = "1d",
    cash: Annotated[float, typer.Option("--cash", help="Initial cash.")] = 100_000.0,
    broker_type: Annotated[
        str, typer.Option("--broker", "-b", help="Broker: ccxt or alpaca.")
    ] = "ccxt",
    exchange: Annotated[str, typer.Option("--exchange", help="CCXT exchange.")] = "binance",
    sandbox: Annotated[bool, typer.Option("--sandbox/--live", help="Use sandbox/testnet.")] = True,
    poll: Annotated[float, typer.Option("--poll", help="Poll interval (seconds).")] = 60.0,
    db: Annotated[
        str, typer.Option("--db", help="SQLite database URL.")
    ] = "sqlite:///gordon_trades.db",
) -> None:
    """Run a live trading session with real order execution."""
    from decimal import Decimal

    import gordon.strategy.templates  # noqa: F401
    from gordon.engine.live import LiveEngine
    from gordon.engine.runner import EngineRunner
    from gordon.persistence import TradeStore
    from gordon.strategy.registry import default_registry

    strat = default_registry.get(strategy)
    if strat is None:
        rprint(f"[red]Unknown strategy:[/red] {strategy}")
        raise typer.Exit(code=1)

    ac = AssetClass.CRYPTO if broker_type == "ccxt" else AssetClass.EQUITY
    assets = [Asset(symbol=s.strip(), asset_class=ac) for s in symbols.split(",")]
    iv = Interval(interval)
    store = TradeStore(db_url=db)

    broker_obj: object
    feed_obj: object

    if broker_type == "ccxt":
        from gordon.broker.ccxt_broker import CCXTBroker
        from gordon.data.providers import CCXTDataFeed

        broker_obj = CCXTBroker(exchange=exchange, sandbox=sandbox)
        feed_obj = CCXTDataFeed(exchange=exchange)
    elif broker_type == "alpaca":
        from gordon.broker.alpaca_broker import AlpacaBroker
        from gordon.data.providers import YFinanceDataFeed

        broker_obj = AlpacaBroker(paper=sandbox)
        feed_obj = YFinanceDataFeed()
    else:
        rprint(f"[red]Unknown broker:[/red] {broker_type}")
        raise typer.Exit(code=1)

    engine = LiveEngine(
        strategies=[strat],
        assets=assets,
        data_feed=feed_obj,  # type: ignore[arg-type]
        broker=broker_obj,
        interval=iv,
        initial_cash=Decimal(str(cash)),
        poll_interval=poll,
        store=store,
    )

    mode = "sandbox" if sandbox else "[red]LIVE[/red]"
    rprint(
        f"[bold]Live trading[/bold] ({mode}) {strategy} on "
        f"{symbols} via {broker_type} — Ctrl+C to stop"
    )
    runner = EngineRunner(engine)
    runner.run()


@app.command()
def agent() -> None:
    """Launch the AI trading agent."""
    rprint("[yellow]Coming in Stage 4[/yellow]")
