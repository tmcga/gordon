# Gordon — Stage 1: Foundation

## Tasks
- [x] Create pyproject.toml with all deps and tool config
- [x] Create project scaffolding (Makefile, .gitignore, LICENSE, directories, __init__.py)
- [x] Build core/ module (models, enums, events, errors, protocols)
- [x] Build config.py (Pydantic Settings with YAML)
- [x] Build data/ module (base, providers, storage)
- [x] Build utils/ (logging, retry, timing)
- [x] Build CLI skeleton (typer)
- [x] Write unit tests (test_models, test_events, test_config)
- [x] Create CI workflow and pre-commit config
- [x] Write README.md
- [x] Verify: make lint, make typecheck, make test all pass

## Review
- Lint (ruff check + format): PASS
- Type check (mypy strict): PASS — 0 errors in 30 files
- Tests (pytest): 89 passed in 0.14s
- All modules import cleanly
- CLI works: `gordon --version`, `gordon data fetch`
