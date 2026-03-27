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
def backtest() -> None:
    """Run a backtest against historical data."""
    rprint("[yellow]Coming in Stage 2[/yellow]")


@app.command()
def paper() -> None:
    """Run a paper-trading session."""
    rprint("[yellow]Coming in Stage 3[/yellow]")


@app.command()
def live() -> None:
    """Run a live trading session."""
    rprint("[yellow]Coming in Stage 3[/yellow]")


@app.command()
def agent() -> None:
    """Launch the AI trading agent."""
    rprint("[yellow]Coming in Stage 4[/yellow]")
