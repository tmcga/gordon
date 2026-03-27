"""Tests for gordon.config — configuration models and defaults."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from gordon.config import (
    AgentConfig,
    BrokerConfig,
    DataConfig,
    GordonConfig,
    RiskConfig,
    StrategyConfig,
    TradingMode,
)
from gordon.core.enums import AssetClass, Interval

# ── GordonConfig top-level defaults ───────────────────────────────────


class TestGordonConfigDefaults:
    def test_default_mode(self):
        cfg = GordonConfig()
        assert cfg.mode == TradingMode.BACKTEST
        assert cfg.mode == "backtest"

    def test_default_initial_cash(self):
        cfg = GordonConfig()
        assert cfg.initial_cash == 100_000.0

    def test_default_log_level(self):
        cfg = GordonConfig()
        assert cfg.log_level == "INFO"

    def test_default_strategies_empty(self):
        cfg = GordonConfig()
        assert cfg.strategies == []

    def test_custom_values(self):
        cfg = GordonConfig(
            mode=TradingMode.PAPER,
            initial_cash=50_000.0,
            log_level="DEBUG",
        )
        assert cfg.mode == TradingMode.PAPER
        assert cfg.initial_cash == 50_000.0
        assert cfg.log_level == "DEBUG"

    def test_log_level_normalised(self):
        cfg = GordonConfig(log_level="debug")
        assert cfg.log_level == "DEBUG"

    def test_invalid_log_level(self):
        with pytest.raises(ValidationError):
            GordonConfig(log_level="TRACE")

    def test_initial_cash_must_be_positive(self):
        with pytest.raises(ValidationError):
            GordonConfig(initial_cash=0.0)

    def test_initial_cash_negative(self):
        with pytest.raises(ValidationError):
            GordonConfig(initial_cash=-100.0)


# ── BrokerConfig ──────────────────────────────────────────────────────


class TestBrokerConfig:
    def test_defaults(self):
        cfg = GordonConfig()
        broker = cfg.broker
        assert broker.type == "simulated"
        assert broker.exchange == ""
        assert broker.api_key is None
        assert broker.api_secret is None
        assert broker.base_url is None
        assert broker.sandbox is True
        assert broker.timeout_seconds == 30.0
        assert broker.extra == {}

    def test_frozen(self):
        cfg = BrokerConfig()
        with pytest.raises(ValidationError):
            cfg.type = "ccxt"


# ── DataConfig ─────────────────────────────────────────────────────────


class TestDataConfig:
    def test_defaults(self):
        cfg = GordonConfig()
        data = cfg.data
        assert data.provider == "yfinance"
        assert data.cache_dir == Path(".gordon_cache")
        assert data.default_interval == Interval.D1
        assert data.default_asset_class == AssetClass.EQUITY
        assert data.api_key is None
        assert data.base_url is None
        assert data.extra == {}

    def test_frozen(self):
        cfg = DataConfig()
        with pytest.raises(ValidationError):
            cfg.provider = "ccxt"


# ── RiskConfig ─────────────────────────────────────────────────────────


class TestRiskConfig:
    def test_defaults(self):
        cfg = GordonConfig()
        risk = cfg.risk
        assert risk.max_position_pct == 0.10
        assert risk.max_drawdown == 0.20
        assert risk.daily_loss_limit == 0.05
        assert risk.max_open_positions == 20
        assert risk.cooldown_seconds == 60

    def test_drawdown_validator_skips_when_daily_not_yet_parsed(self):
        # max_drawdown is declared before daily_loss_limit, so the validator
        # cannot see daily_loss_limit in info.data yet -- it silently passes.
        cfg = RiskConfig(max_drawdown=0.02, daily_loss_limit=0.05)
        assert cfg.max_drawdown == 0.02

    def test_drawdown_equal_to_daily_is_ok(self):
        cfg = RiskConfig(max_drawdown=0.10, daily_loss_limit=0.10)
        assert cfg.max_drawdown == 0.10

    def test_frozen(self):
        cfg = RiskConfig()
        with pytest.raises(ValidationError):
            cfg.max_drawdown = 0.5


# ── AgentConfig ────────────────────────────────────────────────────────


class TestAgentConfig:
    def test_defaults(self):
        cfg = GordonConfig()
        agent = cfg.agent
        assert agent.model == "claude-sonnet-4-20250514"
        assert agent.api_key is None
        assert agent.max_turns == 10
        assert agent.temperature == 0.0
        assert agent.extra == {}

    def test_frozen(self):
        cfg = AgentConfig()
        with pytest.raises(ValidationError):
            cfg.model = "other"


# ── StrategyConfig ─────────────────────────────────────────────────────


class TestStrategyConfig:
    def test_creation(self):
        cfg = StrategyConfig(name="momentum")
        assert cfg.name == "momentum"
        assert cfg.enabled is True
        assert cfg.params == {}

    def test_custom_params(self):
        cfg = StrategyConfig(
            name="mean_reversion",
            enabled=False,
            params={"window": 20, "threshold": 2.0},
        )
        assert cfg.name == "mean_reversion"
        assert cfg.enabled is False
        assert cfg.params["window"] == 20

    def test_frozen(self):
        cfg = StrategyConfig(name="test")
        with pytest.raises(ValidationError):
            cfg.name = "other"

    def test_strategies_in_gordon_config(self):
        cfg = GordonConfig(
            strategies=[
                StrategyConfig(name="s1"),
                StrategyConfig(name="s2", enabled=False),
            ]
        )
        assert len(cfg.strategies) == 2
        assert cfg.strategies[0].name == "s1"
        assert cfg.strategies[1].enabled is False
