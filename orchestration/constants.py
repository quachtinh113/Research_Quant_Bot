"""
Core enumerations shared by every layer of the orchestration engine.

These are the only vocabulary the telemetry schema accepts. Pods, the risk
engine and the orchestrator must speak in these terms; free-form strings are
rejected at the Pydantic boundary.
"""

from enum import Enum


class PodStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CIRCUIT_BREAKER_TRIGGERED = "CIRCUIT_BREAKER_TRIGGERED"
    DRAINING_POSITIONS = "DRAINING_POSITIONS"
    # Terminal state reached only via FleetOrchestrator.stop_pod(); the five
    # mandated states above are the live-lifecycle vocabulary.
    STOPPED = "STOPPED"


class MarketRegime(str, Enum):
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    HIGH_VOL_RANGING = "HIGH_VOL_RANGING"
    LOW_VOL_COMPRESSION = "LOW_VOL_COMPRESSION"
    LIQUIDITY_SHOCK = "LIQUIDITY_SHOCK"


class VolatilityState(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    TWAP = "TWAP"
    LIMIT_MAKER = "LIMIT_MAKER"
    VOLATILITY_LADDER = "VOLATILITY_LADDER"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> "OrderSide":
        return OrderSide.SELL if self is OrderSide.BUY else OrderSide.BUY


class TimeInForce(str, Enum):
    IOC = "IOC"
    GTC = "GTC"
    PostOnly = "PostOnly"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ExecutionMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class ExitReason(str, Enum):
    HARD_STOP = "HARD_STOP"
    TAKE_PROFIT = "TAKE_PROFIT"
    SIGNAL_FLIP = "SIGNAL_FLIP"
    DRAIN = "DRAIN"
    MANUAL = "MANUAL"
