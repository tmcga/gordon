# Gordon — Stage 2: Strategy Framework + Backtesting Engine

## Tasks
- [x] Build strategy framework (base, registry, indicators)
- [x] Build 3 strategy templates (SMA crossover, momentum, mean reversion)
- [x] Build EventBus (typed async event dispatcher)
- [x] Build SimulatedBroker (slippage + commission models)
- [x] Build PortfolioTracker (position tracking, P&L)
- [x] Build BacktestEngine + Clock
- [x] Build risk metrics (Sharpe, Sortino, drawdown, Calmar, win rate)
- [x] Wire CLI backtest command with Rich output
- [x] Write tests (unit + integration + e2e)
- [x] Verify: lint, typecheck, all tests pass

## Review
- Lint (ruff check + format): PASS
- Type check (mypy strict): PASS — 0 errors in 42 files
- Tests (pytest): 176 passed in 1.57s
- CLI `gordon backtest` wired with Rich tables for metrics + trade log
- Event-driven pipeline: MarketEvent -> Strategy -> Signal -> Order -> Broker -> Fill
- Same pipeline shared by BacktestEngine, PaperEngine (Stage 3), LiveEngine (Stage 3)
