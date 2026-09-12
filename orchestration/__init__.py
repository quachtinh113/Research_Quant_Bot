"""
Institutional Multi-Bot Orchestration & Dual-Core Architecture.

Architecture:
- builder_core: Alpha Mining, Data Feeds, Pod Execution, and Fleet Orchestration.
- mentor_core: Central Risk Engine (Aladdin), Circuit Breakers, State Persistence,
               Reconciliation Loop, Rate Limiting & Audit Telemetry.
"""

from . import builder_core
from . import mentor_core

# Builder Core re-exports
from .builder_core import (
    FleetOrchestrator,
    BasePod,
    VolatilityBreakoutPod,
    BarFeed,
    Bar,
    PointInTimeStore,
    CCXTExecutionGateway,
    MarketRules,
    ExecutionResult,
    OrderManager,
    Position,
    PortfolioOptimizer,
)

# Mentor Core re-exports
from .mentor_core import (
    CentralRiskEngine,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerTier,
    StateStore,
    SQLiteStateStore,
    RedisStateStore,
    run_reconciliation,
    RateLimiter,
    rate_limited,
    retry_async,
    TelemetryDispatcher,
)

# Common re-exports
from .constants import (
    PodStatus,
    MarketRegime,
    VolatilityState,
    SignalDirection,
    OrderType,
    OrderSide,
    TimeInForce,
    ExecutionMode,
    OrderStatus,
    ExitReason,
)

__version__ = "3.0.0"

__all__ = [
    "builder_core",
    "mentor_core",
    # Builder Core
    "FleetOrchestrator",
    "BasePod",
    "VolatilityBreakoutPod",
    "BarFeed",
    "Bar",
    "PointInTimeStore",
    "CCXTExecutionGateway",
    "MarketRules",
    "ExecutionResult",
    "OrderManager",
    "Position",
    "PortfolioOptimizer",
    # Mentor Core
    "CentralRiskEngine",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerTier",
    "StateStore",
    "SQLiteStateStore",
    "RedisStateStore",
    "run_reconciliation",
    "RateLimiter",
    "rate_limited",
    "retry_async",
    "TelemetryDispatcher",
    # Constants
    "PodStatus",
    "MarketRegime",
    "VolatilityState",
    "SignalDirection",
    "OrderType",
    "OrderSide",
    "TimeInForce",
    "ExecutionMode",
    "OrderStatus",
    "ExitReason",
]
