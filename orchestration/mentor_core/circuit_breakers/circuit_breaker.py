"""
Two-tier deterministic circuit breaker.

Tier 1 (soft): halve trade risk. Tier 2 (hard): no new risk, drain positions.
A manual kill switch is a Tier 2 condition that only a human operator clears.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Optional, Tuple


class CircuitBreakerTier(str, Enum):
    NORMAL = "NORMAL"
    TIER_1_SOFT_LIMIT = "TIER_1_SOFT_LIMIT"  # Reduce sizing by 50%
    TIER_2_HARD_STOP = "TIER_2_HARD_STOP"  # Emergency halt & drain


@dataclass(frozen=True)
class CircuitBreakerConfig:
    max_drawdown_soft_pct: float = 0.05  # 5% DD -> Tier 1
    max_drawdown_hard_pct: float = 0.08  # 8% DD -> Tier 2
    max_daily_loss_pct: float = 0.03  # 3% daily loss -> Tier 2
    max_consecutive_losses: int = 5  # 5 losses -> Tier 1

    def __post_init__(self) -> None:
        if self.max_drawdown_soft_pct >= self.max_drawdown_hard_pct:
            raise ValueError("soft drawdown limit must be below the hard limit")


class CircuitBreaker:
    def __init__(self, config: Optional[CircuitBreakerConfig] = None) -> None:
        self.config = config or CircuitBreakerConfig()
        self.consecutive_losses = 0
        self.daily_pnl_pct = 0.0
        self.current_drawdown_pct = 0.0
        self.tier = CircuitBreakerTier.NORMAL
        self.kill_switch_reason: Optional[str] = None
        self.last_reason = "Normal operational risk parameters."

    # ---------------------------------------------------------------- inputs
    def register_trade_result(self, pnl_pct: float) -> None:
        self.daily_pnl_pct += pnl_pct
        self.consecutive_losses = self.consecutive_losses + 1 if pnl_pct < 0 else 0

    def update_drawdown(self, current_drawdown_pct: float) -> None:
        self.current_drawdown_pct = max(0.0, float(current_drawdown_pct))

    def reset_daily(self) -> None:
        self.daily_pnl_pct = 0.0

    def engage_kill_switch(self, reason: str) -> None:
        self.kill_switch_reason = reason

    def release_kill_switch(self) -> None:
        """Operator action. Does not clear drawdown-driven states."""
        self.kill_switch_reason = None

    # ------------------------------------------------------------ evaluation
    def evaluate(self) -> Tuple[CircuitBreakerTier, str]:
        cfg = self.config

        if self.kill_switch_reason:
            return self._set(CircuitBreakerTier.TIER_2_HARD_STOP, f"Kill switch engaged: {self.kill_switch_reason}")

        if self.current_drawdown_pct >= cfg.max_drawdown_hard_pct:
            return self._set(
                CircuitBreakerTier.TIER_2_HARD_STOP,
                f"Hard drawdown limit breached: {self.current_drawdown_pct*100:.2f}% >= "
                f"{cfg.max_drawdown_hard_pct*100:.2f}%",
            )

        if self.daily_pnl_pct <= -cfg.max_daily_loss_pct:
            return self._set(
                CircuitBreakerTier.TIER_2_HARD_STOP,
                f"Max daily loss breached: {self.daily_pnl_pct*100:.2f}% <= "
                f"-{cfg.max_daily_loss_pct*100:.2f}%",
            )

        if self.current_drawdown_pct >= cfg.max_drawdown_soft_pct:
            return self._set(
                CircuitBreakerTier.TIER_1_SOFT_LIMIT,
                f"Soft drawdown warning: {self.current_drawdown_pct*100:.2f}% >= "
                f"{cfg.max_drawdown_soft_pct*100:.2f}%",
            )

        if self.consecutive_losses >= cfg.max_consecutive_losses:
            return self._set(
                CircuitBreakerTier.TIER_1_SOFT_LIMIT,
                f"Consecutive loss streak reached: {self.consecutive_losses}",
            )

        return self._set(CircuitBreakerTier.NORMAL, "Normal operational risk parameters.")

    def _set(self, tier: CircuitBreakerTier, reason: str) -> Tuple[CircuitBreakerTier, str]:
        self.tier = tier
        self.last_reason = reason
        return tier, reason

    def snapshot(self) -> dict:
        return {
            "tier": self.tier.value,
            "reason": self.last_reason,
            "consecutive_losses": self.consecutive_losses,
            "daily_pnl_pct": self.daily_pnl_pct,
            "current_drawdown_pct": self.current_drawdown_pct,
            "kill_switch_reason": self.kill_switch_reason,
            "config": asdict(self.config),
        }
