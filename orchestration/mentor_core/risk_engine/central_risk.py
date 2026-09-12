"""
Central Risk Engine (Aladdin pattern).

Every number that leaves this module is a deterministic function of equity,
price, ATR and the configured limits. There is no parameter through which a
signal, a confidence score, a pod or an LLM can enlarge a position, move a
stop, or bypass a breaker. Pods *ask*; the engine *decides*.

    Size = min( Equity x RiskPct / (k x ATR),  MaxGrossExposure x Equity / Price )

subject to the fleet-wide exposure ledger and the two-tier circuit breaker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from orchestration.config import RiskSettings
from orchestration.constants import ExitReason, OrderSide, PodStatus, SignalDirection
from orchestration.mentor_core.circuit_breakers.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerTier


@dataclass(frozen=True)
class RiskLimits:
    max_risk_per_trade_pct: float = 0.01  # 1% of equity at risk per trade
    atr_multiplier_stop: float = 2.0  # k in k x ATR
    atr_multiplier_tp: float = 3.0
    max_gross_exposure_pct: float = 0.50  # single-pod notional cap as fraction of equity
    min_risk_reward_ratio: float = 1.0

    @classmethod
    def from_settings(cls, s: RiskSettings) -> "RiskLimits":
        return cls(
            max_risk_per_trade_pct=s.max_risk_per_trade_pct,
            atr_multiplier_stop=s.atr_multiplier_stop,
            atr_multiplier_tp=s.atr_multiplier_tp,
            max_gross_exposure_pct=s.max_gross_exposure_pct,
            min_risk_reward_ratio=s.min_risk_reward_ratio,
        )


@dataclass
class PositionSizingResult:
    allowed: bool
    units: float
    notional_value: float
    position_pct: float
    stop_loss_price: float
    take_profit_price: float
    risk_reward_ratio: float
    cvar_impact_pct: float
    risk_pct_applied: float = 0.0
    breaker_tier: CircuitBreakerTier = CircuitBreakerTier.NORMAL
    rejection_reason: Optional[str] = None

    @classmethod
    def rejected(cls, reason: str, tier: CircuitBreakerTier = CircuitBreakerTier.NORMAL) -> "PositionSizingResult":
        return cls(
            allowed=False,
            units=0.0,
            notional_value=0.0,
            position_pct=0.0,
            stop_loss_price=0.0,
            take_profit_price=0.0,
            risk_reward_ratio=0.0,
            cvar_impact_pct=0.0,
            breaker_tier=tier,
            rejection_reason=reason,
        )


@dataclass(frozen=True)
class StopEvent:
    reason: ExitReason
    exit_price: float


@dataclass
class ExposureLedger:
    """
    Fleet-wide gross notional book. Shared by every pod's risk engine so the
    aggregate leverage cap is enforced centrally, not per pod.
    """

    max_gross_notional: float
    _book: Dict[str, float] = field(default_factory=dict)

    @property
    def gross_notional(self) -> float:
        return float(sum(self._book.values()))

    def exposure_of(self, pod_id: str) -> float:
        return float(self._book.get(pod_id, 0.0))

    def set_exposure(self, pod_id: str, notional: float) -> None:
        self._book[pod_id] = max(0.0, float(notional))

    def remove(self, pod_id: str) -> None:
        self._book.pop(pod_id, None)

    def headroom(self, pod_id: str) -> float:
        """Notional this pod may add without breaching the fleet cap."""
        others = self.gross_notional - self.exposure_of(pod_id)
        return max(0.0, self.max_gross_notional - others - self.exposure_of(pod_id))

    def leverage(self, fund_equity: float) -> float:
        return self.gross_notional / fund_equity if fund_equity > 0 else 0.0


class CentralRiskEngine:
    """
    Deterministic gatekeeper. Owns the pod's circuit breaker and (optionally)
    a reference to the fleet exposure ledger.
    """

    def __init__(
        self,
        limits: Optional[RiskLimits] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        ledger: Optional[ExposureLedger] = None,
        settings: Optional[RiskSettings] = None,
    ) -> None:
        if settings is not None:
            self.limits = RiskLimits.from_settings(settings)
            cb_cfg = CircuitBreakerConfig(
                max_drawdown_soft_pct=settings.max_drawdown_soft_pct,
                max_drawdown_hard_pct=settings.max_drawdown_hard_pct,
                max_daily_loss_pct=settings.max_daily_loss_pct,
                max_consecutive_losses=settings.max_consecutive_losses,
            )
            self.circuit_breaker = circuit_breaker or CircuitBreaker(cb_cfg)
        else:
            self.limits = limits or RiskLimits()
            self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.ledger = ledger

    # --------------------------------------------------------------- sizing
    def size_position(
        self,
        equity: float,
        price: float,
        atr: float,
        direction: SignalDirection,
        risk_pct: Optional[float] = None,
        notional_cap: Optional[float] = None,
    ) -> PositionSizingResult:
        """
        Pure sizing math. ``risk_pct`` may only be *lowered* (breaker tiers);
        it is clamped to the configured maximum.
        """
        if direction == SignalDirection.NEUTRAL:
            return PositionSizingResult.rejected("Neutral signal: no position.")
        if equity <= 0 or price <= 0 or atr <= 0:
            return PositionSizingResult.rejected("Invalid equity, price or ATR.")

        lim = self.limits
        applied_risk = min(lim.max_risk_per_trade_pct, risk_pct if risk_pct is not None else lim.max_risk_per_trade_pct)
        applied_risk = max(0.0, applied_risk)

        stop_dist = lim.atr_multiplier_stop * atr
        tp_dist = lim.atr_multiplier_tp * atr
        risk_amount = equity * applied_risk

        raw_units = risk_amount / stop_dist
        max_notional = equity * lim.max_gross_exposure_pct
        if notional_cap is not None:
            max_notional = min(max_notional, max(0.0, notional_cap))
        units = min(raw_units, max_notional / price)
        notional = units * price
        if units <= 0 or notional <= 0:
            return PositionSizingResult.rejected("Exposure cap leaves no headroom for a new position.")

        if direction == SignalDirection.BUY:
            sl_price, tp_price = price - stop_dist, price + tp_dist
        else:
            sl_price, tp_price = price + stop_dist, price - tp_dist
        if sl_price <= 0:
            return PositionSizingResult.rejected("Stop price would be non-positive.")

        rr = tp_dist / stop_dist
        if rr < lim.min_risk_reward_ratio:
            return PositionSizingResult.rejected(
                f"Risk/reward {rr:.2f} below minimum {lim.min_risk_reward_ratio:.2f}."
            )

        # Parametric 95% tail proxy on the amount actually at risk (stop distance).
        cvar_impact = (units * stop_dist / equity) * 1.65 * 100.0

        return PositionSizingResult(
            allowed=True,
            units=units,
            notional_value=notional,
            position_pct=notional / equity,
            stop_loss_price=round(sl_price, 8),
            take_profit_price=round(tp_price, 8),
            risk_reward_ratio=round(rr, 4),
            cvar_impact_pct=round(cvar_impact, 4),
            risk_pct_applied=applied_risk,
        )

    def evaluate_order(
        self,
        equity: float,
        price: float,
        atr: float,
        direction: SignalDirection,
        current_drawdown_pct: float = 0.0,
        pod_id: Optional[str] = None,
    ) -> PositionSizingResult:
        """Sizing gated by the circuit breaker and the fleet exposure ledger."""
        self.circuit_breaker.update_drawdown(current_drawdown_pct)
        tier, reason = self.circuit_breaker.evaluate()

        if direction == SignalDirection.NEUTRAL:
            res = PositionSizingResult.rejected("Neutral signal: no position.", tier)
            return res
        if tier == CircuitBreakerTier.TIER_2_HARD_STOP:
            return PositionSizingResult.rejected(f"Circuit breaker Tier 2: {reason}", tier)

        risk_pct = self.limits.max_risk_per_trade_pct
        if tier == CircuitBreakerTier.TIER_1_SOFT_LIMIT:
            risk_pct *= 0.5

        notional_cap = None
        if self.ledger is not None and pod_id is not None:
            notional_cap = self.ledger.headroom(pod_id)

        res = self.size_position(equity, price, atr, direction, risk_pct=risk_pct, notional_cap=notional_cap)
        res.breaker_tier = tier
        if not res.allowed and notional_cap is not None and notional_cap <= 0:
            res.rejection_reason = "Fleet gross exposure cap reached (ExposureLedger)."
        return res

    # ------------------------------------------------------------ hard stops
    def check_hard_stop(
        self,
        side: OrderSide,
        stop_loss: float,
        take_profit: float,
        bar_open: float,
        bar_high: float,
        bar_low: float,
    ) -> Optional[StopEvent]:
        """
        Deterministic exit test against a closed bar. Gaps through the stop
        fill at the bar open (never better than the stop). Stops take priority
        over targets when both are touched in the same bar.
        """
        if side == OrderSide.BUY:
            if stop_loss > 0 and bar_low <= stop_loss:
                return StopEvent(ExitReason.HARD_STOP, min(stop_loss, bar_open))
            if take_profit > 0 and bar_high >= take_profit:
                return StopEvent(ExitReason.TAKE_PROFIT, max(take_profit, bar_open))
        else:
            if stop_loss > 0 and bar_high >= stop_loss:
                return StopEvent(ExitReason.HARD_STOP, max(stop_loss, bar_open))
            if take_profit > 0 and bar_low <= take_profit:
                return StopEvent(ExitReason.TAKE_PROFIT, min(take_profit, bar_open))
        return None

    # ---------------------------------------------------------- drawdown map
    def drawdown_action(self, current_drawdown_pct: float) -> Tuple[CircuitBreakerTier, Optional[PodStatus], str]:
        """
        Map a drawdown reading to the pod status the orchestrator must apply.
        Tier 2 -> DRAINING_POSITIONS (then CIRCUIT_BREAKER_TRIGGERED once flat).
        """
        self.circuit_breaker.update_drawdown(current_drawdown_pct)
        tier, reason = self.circuit_breaker.evaluate()
        if tier == CircuitBreakerTier.TIER_2_HARD_STOP:
            return tier, PodStatus.DRAINING_POSITIONS, reason
        return tier, None, reason
