"""Configuration module for Gordon.

Supports layered configuration via environment variables (GORDON_ prefix)
and YAML config files (gordon.yml / gordon.yaml).  Environment variables
take precedence over YAML values, which take precedence over defaults.
"""

from __future__ import annotations

import logging
from enum import StrEnum, unique
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from gordon.core.enums import AssetClass, Interval

__all__ = [
    "AgentConfig",
    "BrokerConfig",
    "DataConfig",
    "GordonConfig",
    "RiskConfig",
    "StrategyConfig",
    "TradingMode",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums local to configuration
# ---------------------------------------------------------------------------

_YAML_SEARCH_NAMES = ("gordon.yml", "gordon.yaml")


@unique
class TradingMode(StrEnum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


@unique
class BrokerType(StrEnum):
    SIMULATED = "simulated"
    CCXT = "ccxt"
    ALPACA = "alpaca"


@unique
class DataProvider(StrEnum):
    YFINANCE = "yfinance"
    CCXT = "ccxt"
    ALPACA = "alpaca"


# ---------------------------------------------------------------------------
# Nested config models
# ---------------------------------------------------------------------------


class BrokerConfig(BaseModel):
    """Broker connection settings."""

    model_config = {"frozen": True}

    type: BrokerType = BrokerType.SIMULATED
    exchange: str = ""
    api_key: SecretStr | None = None
    api_secret: SecretStr | None = None
    base_url: str | None = None
    sandbox: bool = True
    timeout_seconds: float = 30.0
    extra: dict[str, Any] = Field(default_factory=dict)


class DataConfig(BaseModel):
    """Market data provider settings."""

    model_config = {"frozen": True}

    provider: DataProvider = DataProvider.YFINANCE
    cache_dir: Path = Path(".gordon_cache")
    default_interval: Interval = Interval.D1
    default_asset_class: AssetClass = AssetClass.EQUITY
    api_key: SecretStr | None = None
    base_url: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class RiskConfig(BaseModel):
    """Risk management guardrails."""

    model_config = {"frozen": True}

    max_position_pct: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Maximum portfolio fraction in a single position.",
    )
    max_drawdown: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Maximum tolerable drawdown before halting.",
    )
    daily_loss_limit: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Maximum daily loss as fraction of equity.",
    )
    max_open_positions: int = Field(
        default=20,
        ge=1,
        description="Maximum number of concurrent open positions.",
    )
    cooldown_seconds: int = Field(
        default=60,
        ge=0,
        description="Seconds to pause trading after a risk limit breach.",
    )

    @field_validator("max_drawdown")
    @classmethod
    def _drawdown_exceeds_daily(cls, v: float, info: Any) -> float:
        daily = info.data.get("daily_loss_limit")
        if daily is not None and v < daily:
            msg = "max_drawdown must be >= daily_loss_limit"
            raise ValueError(msg)
        return v


class AgentConfig(BaseModel):
    """AI agent / LLM settings."""

    model_config = {"frozen": True}

    model: str = "claude-sonnet-4-20250514"
    api_key: SecretStr | None = None
    max_turns: int = Field(default=10, ge=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    extra: dict[str, Any] = Field(default_factory=dict)


class StrategyConfig(BaseModel):
    """Configuration for a single trading strategy."""

    model_config = {"frozen": True}

    name: str
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# YAML settings source
# ---------------------------------------------------------------------------


class YamlSettingsSource(PydanticBaseSettingsSource):
    """Load settings from a YAML file if present in the working directory."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._yaml_data: dict[str, Any] = self._load_yaml()

    @staticmethod
    def _load_yaml() -> dict[str, Any]:
        for name in _YAML_SEARCH_NAMES:
            path = Path(name)
            if path.is_file():
                logger.debug("Loading config from %s", path)
                with path.open() as fh:
                    data = yaml.safe_load(fh)
                return data if isinstance(data, dict) else {}
        return {}

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        value = self._yaml_data.get(field_name)
        return value, field_name, False

    def __call__(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field_name in self.settings_cls.model_fields:
            value, _, _ = self.get_field_value(None, field_name)
            if value is not None:
                result[field_name] = value
        return result


# ---------------------------------------------------------------------------
# Top-level settings
# ---------------------------------------------------------------------------


class GordonConfig(BaseSettings):
    """Top-level Gordon configuration.

    Resolution order (highest precedence first):
        1. Environment variables (prefixed ``GORDON_``)
        2. YAML config file (``gordon.yml`` / ``gordon.yaml``)
        3. Field defaults
    """

    model_config = SettingsConfigDict(
        env_prefix="GORDON_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # -- top-level knobs -----------------------------------------------------
    mode: TradingMode = TradingMode.BACKTEST
    initial_cash: float = Field(default=100_000.0, gt=0.0)
    log_level: str = "INFO"

    # -- nested sections -----------------------------------------------------
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    strategies: list[StrategyConfig] = Field(default_factory=list)

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, v: str) -> str:
        v = v.upper()
        if v not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            msg = f"Invalid log_level: {v!r}"
            raise ValueError(msg)
        return v

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Inject YAML between env vars and defaults."""
        return (
            init_settings,
            env_settings,
            YamlSettingsSource(settings_cls),
            file_secret_settings,
        )
