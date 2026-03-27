"""Domain enumerations for Gordon."""

from enum import StrEnum, unique


@unique
class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


@unique
class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


@unique
class TimeInForce(StrEnum):
    GTC = "gtc"  # Good 'til cancelled
    IOC = "ioc"  # Immediate or cancel
    FOK = "fok"  # Fill or kill
    DAY = "day"  # Day order


@unique
class AssetClass(StrEnum):
    EQUITY = "equity"
    CRYPTO = "crypto"
    FOREX = "forex"
    FUTURES = "futures"
    OPTION = "option"


@unique
class Interval(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"
    MO1 = "1mo"


@unique
class OrderStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@unique
class SignalType(StrEnum):
    LONG = "long"
    SHORT = "short"
    EXIT = "exit"
