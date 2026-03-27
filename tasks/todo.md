# Gordon — Stage 3: Paper Trading + Live Trading

## Tasks
- [x] Build trade persistence layer (SQLAlchemy + SQLite)
- [x] Build CCXT broker adapter (real crypto order routing)
- [x] Build Alpaca broker adapter (real equity order routing)
- [x] Build live data feed (polling-based streaming)
- [x] Build PaperEngine (live data + simulated fills)
- [x] Build LiveEngine (live data + real fills)
- [x] Add graceful shutdown (SIGINT/SIGTERM via EngineRunner)
- [x] Wire CLI paper and live commands
- [x] Write tests (persistence, live data, helpers, paper engine, runner)
- [x] Verify: lint, typecheck, all tests pass

## Review
- Lint (ruff check + format): PASS
- Type check (mypy strict): PASS — 0 errors in 52 files
- Tests (pytest): 200 passed in 2.13s
- CLI: `gordon paper` and `gordon live` fully wired
- Shared helpers extracted from BacktestEngine into _helpers.py
- Same event pipeline for backtest/paper/live — only DataFeed and Broker differ
