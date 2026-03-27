# Gordon — Stage 5: Risk Management + Portfolio Optimization

## Tasks
- [x] Build RiskManager (composable guard pipeline)
- [x] Build risk guards (position size, concentration, cooldown, drawdown, whitelist)
- [x] Build position sizing (Kelly, fixed fractional, volatility-targeted)
- [x] Build portfolio optimizer (mean-variance, risk parity, Black-Litterman)
- [x] Build rebalancer (target-weight order generation)
- [x] Wire optimizer into agent tools + CLI command
- [x] Write tests (guards, manager, sizing, limits, optimizer, rebalancer)
- [x] Verify: lint, typecheck, all tests pass

## Review
- Lint (ruff check + format): PASS
- Type check (mypy strict): PASS — 0 errors in 64 files
- Tests (pytest): 303 passed in 2.69s
- CLI: `gordon optimize --symbols AAPL,MSFT,GOOG --method mean-variance`
- 6 risk guards, 3 position sizers, 3 optimizer methods, rebalancer
