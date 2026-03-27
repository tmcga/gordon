"""Error hierarchy for Gordon."""


class GordonError(Exception):
    """Base exception for all Gordon errors."""


class ConfigError(GordonError):
    """Invalid or missing configuration."""


class DataError(GordonError):
    """Market data fetch or processing failure."""


class BrokerError(GordonError):
    """Broker communication or order execution failure."""


class OrderRejectedError(BrokerError):
    """Order rejected by risk guard or broker."""

    def __init__(self, reason: str, order_id: str | None = None) -> None:
        self.reason = reason
        self.order_id = order_id
        super().__init__(f"Order rejected: {reason}")


class StrategyError(GordonError):
    """Error in strategy execution."""


class InsufficientDataError(DataError):
    """Not enough historical data for the requested operation."""
