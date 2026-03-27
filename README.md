# Gordon

**AI-powered trading agent with backtesting, risk management, and portfolio optimization.**

[![CI](https://github.com/tmcga/gordon/actions/workflows/ci.yml/badge.svg)](https://github.com/tmcga/gordon/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

---

## What is Gordon?

Gordon is an open-source Python trading agent that combines quantitative finance with AI reasoning. Built on an event-driven architecture, it provides a unified pipeline where backtesting, paper trading, and live execution share the same strategy and risk management code. Write a strategy once, validate it against historical data, then deploy it to live markets with zero changes.

## Key Features

- **Event-driven architecture** -- backtest, paper, and live modes share a single execution pipeline
- **Strategy framework** -- write a complete strategy in roughly 20 lines of Python
- **Backtesting engine** -- full performance metrics including Sharpe ratio, Sortino ratio, and max drawdown
- **Multi-asset support** -- crypto via CCXT (100+ exchanges) and US equities via Alpaca
- **AI agent powered by Claude** -- analyze markets, backtest strategies, optimize parameters, then trade
- **Risk management pipeline** -- position limits, drawdown guards, and Kelly criterion sizing
- **Portfolio optimization** -- mean-variance, risk parity, and Black-Litterman models
- **Type-safe** -- Pydantic models throughout, mypy strict mode

## Quick Start

```bash
git clone https://github.com/tmcga/gordon.git
cd gordon
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Fetch historical data and run a backtest:

```bash
gordon data fetch AAPL --start 2023-01-01 --end 2024-01-01
```

## Architecture

Gordon's core is an event pipeline that decouples market data ingestion from strategy logic, risk checks, and order execution:

```
MarketEvent --> Strategy --> SignalEvent --> RiskManager --> OrderEvent --> Broker --> FillEvent
```

The key insight is that `BacktestEngine`, `PaperEngine`, and `LiveEngine` each inject different `DataFeed` and `Broker` implementations into the same pipeline. A `BacktestEngine` replays historical bars through a simulated broker. A `LiveEngine` streams real-time data and routes orders to an exchange. The strategy and risk management layers are identical in both cases.

## Project Structure

```
src/gordon/
    core/           Core domain models, events, enums, errors, and protocols
    data/           Market data fetching, normalization, and storage
    strategy/       Strategy base classes and built-in templates
    engine/         Backtest, paper, and live execution engines
    broker/         Broker adapters (Alpaca, CCXT, simulated)
    risk/           Risk management pipeline and guards
    portfolio/      Portfolio optimization (mean-variance, risk parity, Black-Litterman)
    agent/          AI agent integration (Claude-powered analysis and trading)
    web/            Web dashboard routes (FastAPI)
    cli.py          Command-line interface
    config.py       Configuration management
    utils/          Logging, retry logic, and timing utilities
```

## Comparison vs Open Alice

| Capability              | Gordon                        | Open Alice                   |
|-------------------------|-------------------------------|------------------------------|
| Backtesting engine      | Built-in, event-driven        | Not included                 |
| Strategy framework      | Base classes + templates       | Ad-hoc scripts               |
| Risk management         | Pipeline with pluggable guards | Manual checks                |
| Portfolio optimization  | MVO, risk parity, BL          | Not included                 |
| Multi-asset             | Crypto + equities              | Crypto only                  |
| Test suite              | pytest + coverage              | Minimal                      |
| CI/CD                   | GitHub Actions                 | Not configured               |
| Type safety             | Pydantic + mypy strict         | Partial                      |

## Roadmap

- [x] Stage 1: Foundation (core models, market data, CLI)
- [ ] Stage 2: Strategy framework + backtesting engine
- [ ] Stage 3: Paper trading + live trading
- [ ] Stage 4: AI agent integration (Claude)
- [ ] Stage 5: Risk management + portfolio optimization
- [ ] Stage 6: Web dashboard (React + FastAPI)

## Contributing

Contributions are welcome. Please open an issue to discuss proposed changes before submitting a pull request. See the [issue tracker](https://github.com/tmcga/gordon/issues) for open tasks and feature requests.

## License

[MIT](LICENSE)
