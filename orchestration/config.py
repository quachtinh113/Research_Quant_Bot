"""
Pydantic-based settings and pod configuration.

All tunables live here so that risk limits, execution mode and telemetry
endpoints are declared once and injected, never hard-coded inside pods.

Environment overrides use the ``ORCH_`` prefix with ``__`` as the nested
delimiter, e.g. ``ORCH_RISK__MAX_RISK_PER_TRADE_PCT=0.005``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

try:  # pydantic-settings is optional; fall back to a plain model.
    from pydantic_settings import BaseSettings, SettingsConfigDict

    _HAS_SETTINGS = True
except ImportError:  # pragma: no cover
    BaseSettings = BaseModel  # type: ignore[misc,assignment]
    SettingsConfigDict = dict  # type: ignore[misc,assignment]
    _HAS_SETTINGS = False


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent


class RiskSettings(BaseModel):
    """Deterministic risk limits consumed by the Central Risk Engine."""

    max_risk_per_trade_pct: float = Field(0.01, gt=0.0, le=0.2)
    atr_multiplier_stop: float = Field(2.0, gt=0.0, description="k in the k x ATR hard stop")
    atr_multiplier_tp: float = Field(3.0, gt=0.0)
    max_gross_exposure_pct: float = Field(0.50, gt=0.0, le=10.0)
    min_risk_reward_ratio: float = Field(1.0, ge=0.0)
    max_drawdown_soft_pct: float = Field(0.05, gt=0.0, lt=1.0)
    max_drawdown_hard_pct: float = Field(0.08, gt=0.0, lt=1.0)
    max_daily_loss_pct: float = Field(0.03, gt=0.0, lt=1.0)
    max_consecutive_losses: int = Field(5, ge=1)


class ExecutionSettings(BaseModel):
    exchange_id: str = "binance"
    live: bool = False
    api_key: Optional[str] = None
    secret: Optional[str] = None
    default_max_slippage_bps: int = Field(5, ge=0)
    order_timeout_sec: float = Field(10.0, gt=0.0)
    taker_fee_bps: float = Field(6.0, ge=0.0)
    maker_fee_bps: float = Field(2.0, ge=0.0)
    sim_market_slippage_bps: float = Field(3.0, ge=0.0)
    sim_limit_slippage_bps: float = Field(0.0, ge=0.0)


class TelemetrySettings(BaseModel):
    openalgo_host: Optional[str] = None  # e.g. http://127.0.0.1:5000
    openalgo_api_key: Optional[str] = None
    openalgo_strategy: str = "AgentFundQuant"
    openalgo_exchange: str = "CRYPTO"
    openalgo_product: str = "MIS"
    webhook_url: Optional[str] = None  # generic JSON webhook (OpenAlgo strategy webhook or other)
    jsonl_path: Optional[Path] = None  # local append-only telemetry log
    ws_host: Optional[str] = None  # if set, a WebSocket broadcaster is started
    ws_port: int = 8765
    http_timeout_sec: float = 3.0


class DataSettings(BaseModel):
    arctic_uri: str = "lmdb://./data_store"
    library_name: str = "market_data"
    fallback_dir: Path = PROJECT_ROOT / "data_store"
    bar_interval: str = "5min"
    index_is_open_time: bool = False


class PersistenceSettings(BaseModel):
    backend: str = Field("memory", pattern="^(memory|sqlite|redis)$")
    sqlite_path: Path = PACKAGE_ROOT / "state.sqlite"
    redis_url: str = "redis://localhost:6379/0"


class RateLimitSettings(BaseModel):
    tokens: int = Field(100, ge=1)
    period_sec: float = Field(60.0, gt=0.0)
    retry_max_attempts: int = Field(3, ge=1)
    retry_base_delay_sec: float = Field(0.5, ge=0.0)
    retry_factor: float = Field(2.0, ge=1.0)
    retry_max_delay_sec: float = Field(10.0, ge=0.0)


class FleetSettings(BaseModel):
    total_fund_equity: float = Field(1_000_000.0, gt=0.0)
    max_fund_drawdown_pct: float = Field(0.10, gt=0.0, lt=1.0)
    max_total_leverage: float = Field(2.0, gt=0.0)
    health_check_interval_sec: float = Field(5.0, gt=0.0)
    hrp_min_history: int = Field(5, ge=2)
    hrp_method: str = Field("HRP", pattern="^(HRP|CVaR|EQUAL)$")
    stale_bar_tolerance_sec: float = Field(900.0, gt=0.0)


class PodConfig(BaseModel):
    """Declarative description of one pod instance."""

    instance_id: str
    symbol: str
    strategy: str = "volatility_breakout"
    initial_equity: float = Field(100_000.0, gt=0.0)
    bar_interval: str = "5min"
    lookback_period: int = Field(20, ge=2)
    atr_period: int = Field(14, ge=2)
    params: Dict[str, Any] = Field(default_factory=dict)
    risk: Optional[RiskSettings] = None  # per-pod override of fleet defaults


class OrchestrationSettings(BaseSettings):  # type: ignore[misc]
    """Top-level settings tree."""

    if _HAS_SETTINGS:
        model_config = SettingsConfigDict(
            env_prefix="ORCH_", env_nested_delimiter="__", extra="ignore"
        )

    risk: RiskSettings = Field(default_factory=RiskSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    data: DataSettings = Field(default_factory=DataSettings)
    persistence: PersistenceSettings = Field(default_factory=PersistenceSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    fleet: FleetSettings = Field(default_factory=FleetSettings)
    pods: list[PodConfig] = Field(default_factory=list)


def load_settings(**overrides: Any) -> OrchestrationSettings:
    """Build settings from environment plus explicit overrides."""
    return OrchestrationSettings(**overrides)


# Backwards-compatible module-level constants (used by rate_limit/persistence).
_defaults = OrchestrationSettings()
STATE_BACKEND = _defaults.persistence.backend
SQLITE_DB_PATH = _defaults.persistence.sqlite_path
REDIS_URL = _defaults.persistence.redis_url
RATE_LIMIT_TOKENS = _defaults.rate_limit.tokens
RATE_LIMIT_PERIOD = _defaults.rate_limit.period_sec
RETRY_INITIAL = _defaults.rate_limit.retry_base_delay_sec
RETRY_FACTOR = _defaults.rate_limit.retry_factor
RETRY_MAX = _defaults.rate_limit.retry_max_delay_sec
RECONCILIATION_INTERVAL = 30
