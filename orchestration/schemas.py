"""
Standardized institutional telemetry and pod data schemas (Section IV).

``InstitutionalTelemetryPayload`` (alias ``TelemetryPayload``) is the single
wire format every pod emits on every bar. Every field is typed against the
enums in :mod:`orchestration.constants`; anything else is rejected.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .constants import (
    MarketRegime,
    OrderSide,
    OrderType,
    PodStatus,
    SignalDirection,
    TimeInForce,
    VolatilityState,
)


class RegimeSchema(BaseModel):
    type: MarketRegime
    volatility_state: VolatilityState
    liquidity_assessment: str


class SignalSchema(BaseModel):
    direction: SignalDirection
    confidence_score: float = Field(..., ge=-1.0, le=1.0)
    primary_factors: List[str]


class RiskParametersSchema(BaseModel):
    recommended_position_pct: float = Field(..., ge=0.0, le=10.0)
    portfolio_hrp_weight: float = Field(..., ge=0.0, le=1.0)
    entry_range: Tuple[float, float]
    hard_stop_loss: float = Field(..., ge=0.0)
    take_profit_targets: Tuple[float, float]
    risk_reward_ratio: float = Field(..., ge=0.0)
    cvar_impact_pct: float
    risk_engine_reason: Optional[str] = None  # populated when the Central Risk Engine rejects

    @field_validator("entry_range")
    @classmethod
    def _ordered_entry(cls, v: Tuple[float, float]) -> Tuple[float, float]:
        lo, hi = v
        if lo > hi:
            raise ValueError("entry_range must be (low, high)")
        return v


class ExecutionParamsSchema(BaseModel):
    timeInForce: TimeInForce = TimeInForce.GTC
    max_slippage_bps: int = Field(5, ge=0)


class ExecutionPayloadSchema(BaseModel):
    exchange_standard: Literal["CCXT"] = "CCXT"
    order_type: OrderType
    side: OrderSide
    price: float = Field(..., ge=0.0)
    amount: float = Field(..., ge=0.0)
    params: ExecutionParamsSchema = Field(default_factory=ExecutionParamsSchema)


class ChartMarkerSchema(BaseModel):
    """TradingView lightweight-charts series marker."""

    time: int = Field(..., ge=0, description="Unix seconds (UTC)")
    position: Literal["aboveBar", "belowBar", "inBar"]
    color: str
    shape: Literal["arrowUp", "arrowDown", "circle", "square"]
    text: str


class DashboardTelemetrySchema(BaseModel):
    live_pnl_usd: float
    unrealized_pnl_pct: float
    current_drawdown_pct: float = Field(..., ge=0.0)
    margin_utilization_pct: float = Field(..., ge=0.0)
    equity_usd: Optional[float] = None
    open_position: Optional[Dict[str, Any]] = None
    circuit_breaker_tier: Optional[str] = None
    chart_markers: List[ChartMarkerSchema] = Field(default_factory=list)


class InstitutionalTelemetryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    symbol: str
    status: PodStatus
    regime: RegimeSchema
    signal: SignalSchema
    risk_parameters: RiskParametersSchema
    execution_payload: ExecutionPayloadSchema
    dashboard_telemetry: DashboardTelemetrySchema
    analytical_thesis: str

    @field_validator("timestamp")
    @classmethod
    def _iso_timestamp(cls, v: str) -> str:
        # Must parse as ISO-8601; normalise to UTC.
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    @model_validator(mode="after")
    def _side_matches_signal(self) -> "InstitutionalTelemetryPayload":
        d = self.signal.direction
        s = self.execution_payload.side
        if d == SignalDirection.BUY and s != OrderSide.BUY:
            raise ValueError("execution side must be buy for a BUY signal")
        if d == SignalDirection.SELL and s != OrderSide.SELL:
            raise ValueError("execution side must be sell for a SELL signal")
        return self


TelemetryPayload = InstitutionalTelemetryPayload

MANDATED_TOP_LEVEL_FIELDS = (
    "instance_id",
    "timestamp",
    "symbol",
    "status",
    "regime",
    "signal",
    "risk_parameters",
    "execution_payload",
    "dashboard_telemetry",
    "analytical_thesis",
)


class OpenAlgoOrderRequest(BaseModel):
    """Body for POST /api/v1/placeorder on an OpenAlgo host."""

    apikey: str
    strategy: str
    symbol: str
    action: Literal["BUY", "SELL"]
    exchange: str
    pricetype: Literal["MARKET", "LIMIT", "SL", "SL-M"] = "MARKET"
    product: Literal["MIS", "NRML", "CNC"] = "MIS"
    quantity: float = Field(..., gt=0.0)
    price: float = Field(0.0, ge=0.0)
    trigger_price: float = Field(0.0, ge=0.0)
    disclosed_quantity: int = Field(0, ge=0)


class PodHealthSchema(BaseModel):
    instance_id: str
    symbol: str
    status: PodStatus
    worker_alive: bool
    equity_usd: float
    drawdown_pct: float
    gross_notional_usd: float
    last_bar_time: Optional[str] = None
    bars_processed: int = 0
    circuit_breaker_tier: str
    stale: bool = False
    hrp_weight: float = 0.0


class FleetStatusSchema(BaseModel):
    timestamp: str
    total_fund_equity: float
    peak_fund_equity: float
    fund_drawdown_pct: float
    gross_notional_usd: float
    gross_leverage: float
    total_realized_pnl: float
    active_pods: int
    total_registered_pods: int
    global_circuit_breaker: bool
    global_breaker_reason: Optional[str] = None
    pod_statuses: Dict[str, PodStatus]
    pod_weights: Dict[str, float]
    pods: List[PodHealthSchema] = Field(default_factory=list)
