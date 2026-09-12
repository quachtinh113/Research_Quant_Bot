"""
Fleet orchestrator: multi-pod lifecycle supervisor and fund-level risk desk.

* Each pod runs as its own asyncio task fed by its own bar feed.
* A single ExposureLedger caps gross notional across the whole fleet.
* Fund drawdown >= MaxDD flips every pod to DRAINING_POSITIONS and then
  CIRCUIT_BREAKER_TRIGGERED; the flag can only be cleared by an operator.
* HRP / CVaR weights are recomputed from pod bar-returns as history accrues.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from orchestration.config import FleetSettings
from orchestration.constants import ExitReason, PodStatus
from orchestration.builder_core.feed.bar_feed import Bar
from orchestration.builder_core.pods.base_pod import BasePod
from orchestration.mentor_core.risk_engine.central_risk import ExposureLedger
from orchestration.builder_core.allocation.portfolio_hrp import PortfolioOptimizer
from orchestration.schemas import FleetStatusSchema, InstitutionalTelemetryPayload, PodHealthSchema

logger = logging.getLogger(__name__)


class FleetOrchestrator:
    def __init__(
        self,
        total_fund_equity: float = 1_000_000.0,
        max_fund_drawdown_pct: float = 0.10,
        max_total_leverage: float = 2.0,
        settings: Optional[FleetSettings] = None,
        optimizer: Optional[PortfolioOptimizer] = None,
        rebalance_every_bars: int = 10,
    ) -> None:
        self.settings = settings or FleetSettings(
            total_fund_equity=total_fund_equity,
            max_fund_drawdown_pct=max_fund_drawdown_pct,
            max_total_leverage=max_total_leverage,
        )
        s = self.settings
        self.total_fund_equity = s.total_fund_equity
        # Peak is tracked over the equity actually deployed in registered pods.
        self.peak_fund_equity = 0.0
        self.max_fund_drawdown_pct = s.max_fund_drawdown_pct
        self.max_total_leverage = s.max_total_leverage
        self.ledger = ExposureLedger(max_gross_notional=s.total_fund_equity * s.max_total_leverage)
        self.portfolio_optimizer = optimizer or PortfolioOptimizer(method=s.hrp_method)
        self.rebalance_every_bars = rebalance_every_bars

        self.pods: Dict[str, BasePod] = {}
        self.pod_returns: Dict[str, List[float]] = {}
        self.workers: Dict[str, asyncio.Task] = {}
        self.is_global_circuit_breaker_triggered = False
        self.global_breaker_reason: Optional[str] = None
        self.fund_drawdown_pct = 0.0
        self._bars_since_rebalance = 0
        self._lock: Optional[asyncio.Lock] = None
        self.event_log: List[Dict[str, Any]] = []

    # ============================================================ registry
    def register_pod(self, pod: BasePod) -> None:
        if pod.instance_id in self.pods:
            raise ValueError(f"Pod {pod.instance_id} already registered")
        self.pods[pod.instance_id] = pod
        self.pod_returns[pod.instance_id] = []
        if pod.risk_engine.ledger is None:
            pod.risk_engine.ledger = self.ledger
        self.ledger.set_exposure(pod.instance_id, pod.order_manager.gross_notional)
        self.peak_fund_equity = self.fund_equity()
        self._log("register", pod.instance_id)
        self.rebalance_hrp_weights()

    def unregister_pod(self, instance_id: str) -> None:
        self.pods.pop(instance_id, None)
        self.pod_returns.pop(instance_id, None)
        self.workers.pop(instance_id, None)
        self.ledger.remove(instance_id)
        self.peak_fund_equity = self.fund_equity()
        self._log("unregister", instance_id)
        self.rebalance_hrp_weights()

    # =========================================================== lifecycle
    def start_pod(self, instance_id: str, feed: Any, pace_seconds: float = 0.0) -> asyncio.Task:
        pod = self._pod(instance_id)
        if self.is_global_circuit_breaker_triggered:
            raise RuntimeError("Global circuit breaker is engaged; release it before starting pods.")
        if instance_id in self.workers and not self.workers[instance_id].done():
            raise RuntimeError(f"Pod {instance_id} already running")
        pod.start()
        task = asyncio.create_task(pod.run(feed, pace_seconds, after_bar=self._after_pod_bar), name=f"pod:{instance_id}")
        self.workers[instance_id] = task
        self._log("start", instance_id)
        return task

    async def stop_pod(self, instance_id: str, flatten: bool = True) -> None:
        pod = self._pod(instance_id)
        pod.stop()
        task = self.workers.get(instance_id)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if flatten:
            await pod.flatten_now(ExitReason.MANUAL)
        pod.status = PodStatus.STOPPED
        self.ledger.set_exposure(instance_id, pod.order_manager.gross_notional)
        self._log("stop", instance_id)

    def pause_pod(self, instance_id: str) -> None:
        self._pod(instance_id).pause()
        self._log("pause", instance_id)

    def resume_pod(self, instance_id: str) -> None:
        if self.is_global_circuit_breaker_triggered:
            raise RuntimeError("Global circuit breaker is engaged.")
        self._pod(instance_id).resume()
        self._log("resume", instance_id)

    async def step_pod(self, instance_id: str, bar: Bar, history_df: pd.DataFrame) -> Optional[InstitutionalTelemetryPayload]:
        """Synchronous single-bar stepping (tests / research replay)."""
        pod = self.pods.get(instance_id)
        if pod is None:
            return None
        telemetry = await pod.on_bar(bar, history_df)
        await self._after_pod_bar(pod, telemetry)
        return telemetry

    async def run(self, feeds: Dict[str, Any], pace_seconds: float = 0.0) -> None:
        """Start every listed pod on its feed and supervise until all workers finish."""
        for instance_id, feed in feeds.items():
            self.start_pod(instance_id, feed, pace_seconds)
        supervisor = asyncio.create_task(self._supervisor_loop(), name="fleet-supervisor")
        try:
            await asyncio.gather(*self.workers.values(), return_exceptions=True)
        finally:
            supervisor.cancel()
            try:
                await supervisor
            except (asyncio.CancelledError, Exception):
                pass

    async def shutdown(self) -> None:
        for instance_id in list(self.workers):
            await self.stop_pod(instance_id, flatten=False)
        for pod in self.pods.values():
            await pod.execution_gateway.close()
            await pod.telemetry_dispatcher.close()

    # =============================================================== hooks
    async def _after_pod_bar(self, pod: BasePod, telemetry: InstitutionalTelemetryPayload) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            self.pod_returns[pod.instance_id].append(pod.last_bar_return)
            self._bars_since_rebalance += 1
            await self.evaluate_fund_level_risk()
            if self._bars_since_rebalance >= self.rebalance_every_bars:
                self.rebalance_hrp_weights()
                self._bars_since_rebalance = 0

    async def _supervisor_loop(self) -> None:
        interval = self.settings.health_check_interval_sec
        while True:
            await asyncio.sleep(interval)
            report = self.health_check()
            for p in report.pods:
                if p.stale:
                    logger.warning("Pod %s stale: last bar %s", p.instance_id, p.last_bar_time)

    # ============================================================ fund risk
    def fund_equity(self) -> float:
        return float(sum(p.order_manager.current_equity for p in self.pods.values()))

    def aggregate_exposure(self) -> Dict[str, Any]:
        eq = self.fund_equity()
        gross = self.ledger.gross_notional
        return {
            "gross_notional_usd": round(gross, 2),
            "gross_leverage": round(gross / eq, 4) if eq > 0 else 0.0,
            "max_gross_notional_usd": round(self.ledger.max_gross_notional, 2),
            "per_pod": {pid: round(self.ledger.exposure_of(pid), 2) for pid in self.pods},
        }

    async def evaluate_fund_level_risk(self) -> bool:
        """Deterministic fund-level kill switch. Returns True while healthy."""
        eq = self.fund_equity()
        if eq > self.peak_fund_equity:
            self.peak_fund_equity = eq
        self.fund_drawdown_pct = (self.peak_fund_equity - eq) / self.peak_fund_equity if self.peak_fund_equity > 0 else 0.0
        if self.is_global_circuit_breaker_triggered:
            return False
        if self.fund_drawdown_pct >= self.max_fund_drawdown_pct:
            reason = (
                f"Global fund drawdown {self.fund_drawdown_pct*100:.2f}% >= "
                f"{self.max_fund_drawdown_pct*100:.2f}% limit"
            )
            await self.engage_global_circuit_breaker(reason)
            return False
        return True

    async def engage_global_circuit_breaker(self, reason: str) -> None:
        self.is_global_circuit_breaker_triggered = True
        self.global_breaker_reason = reason
        self._log("global_breaker", reason)
        logger.error("GLOBAL CIRCUIT BREAKER: %s", reason)
        for pod in self.pods.values():
            if pod.status == PodStatus.STOPPED:
                continue
            pod.trigger_circuit_breaker(reason)
            await pod.flatten_now(ExitReason.DRAIN)
            if not pod.order_manager.has_position(pod.symbol):
                pod.status = PodStatus.CIRCUIT_BREAKER_TRIGGERED
            self.ledger.set_exposure(pod.instance_id, pod.order_manager.gross_notional)

    def release_global_circuit_breaker(self) -> None:
        """Operator action after review. Pods return to PAUSED, not RUNNING."""
        self.is_global_circuit_breaker_triggered = False
        self.global_breaker_reason = None
        self.peak_fund_equity = self.fund_equity()
        for pod in self.pods.values():
            pod.release_circuit_breaker()
        self._log("global_breaker_released", "")

    # ================================================================= HRP
    def rebalance_hrp_weights(self) -> Dict[str, float]:
        active = [pid for pid, p in self.pods.items() if p.status in (PodStatus.RUNNING, PodStatus.INITIALIZING, PodStatus.PAUSED)]
        if not active:
            return {}
        for pid, p in self.pods.items():
            if pid not in active:
                p.hrp_portfolio_weight = 0.0
        if len(active) == 1:
            self.pods[active[0]].hrp_portfolio_weight = 1.0
            return {active[0]: 1.0}

        min_len = min(len(self.pod_returns[pid]) for pid in active)
        if min_len < self.settings.hrp_min_history:
            w = 1.0 / len(active)
            for pid in active:
                self.pods[pid].hrp_portfolio_weight = w
            return {pid: w for pid in active}

        df = pd.DataFrame({pid: self.pod_returns[pid][-min_len:] for pid in active})
        if (df.std() == 0).all():
            w = 1.0 / len(active)
            weights = {pid: w for pid in active}
        else:
            weights = self.portfolio_optimizer.optimize_weights(df)
        for pid in active:
            self.pods[pid].hrp_portfolio_weight = float(weights.get(pid, 1.0 / len(active)))
        return weights

    # ============================================================== health
    def health_check(self) -> FleetStatusSchema:
        now = time.monotonic()
        tol = self.settings.stale_bar_tolerance_sec
        pods: List[PodHealthSchema] = []
        for pod in self.pods.values():
            h = pod.health()
            stale = (
                pod.status == PodStatus.RUNNING
                and pod.last_bar_wall_time is not None
                and (now - pod.last_bar_wall_time) > tol
            )
            pods.append(PodHealthSchema(**h, stale=stale))
        eq = self.fund_equity()
        exposure = self.aggregate_exposure()
        return FleetStatusSchema(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_fund_equity=round(eq, 2),
            peak_fund_equity=round(self.peak_fund_equity, 2),
            fund_drawdown_pct=round(self.fund_drawdown_pct * 100.0, 4),
            gross_notional_usd=exposure["gross_notional_usd"],
            gross_leverage=exposure["gross_leverage"],
            total_realized_pnl=round(sum(p.order_manager.realized_pnl for p in self.pods.values()), 2),
            active_pods=sum(1 for p in self.pods.values() if p.status == PodStatus.RUNNING),
            total_registered_pods=len(self.pods),
            global_circuit_breaker=self.is_global_circuit_breaker_triggered,
            global_breaker_reason=self.global_breaker_reason,
            pod_statuses={pid: p.status for pid, p in self.pods.items()},
            pod_weights={pid: round(p.hrp_portfolio_weight, 6) for pid, p in self.pods.items()},
            pods=pods,
        )

    def get_fleet_status_summary(self) -> Dict[str, Any]:
        return self.health_check().model_dump(mode="json")

    # =============================================================== utils
    def _pod(self, instance_id: str) -> BasePod:
        if instance_id not in self.pods:
            raise KeyError(f"Unknown pod {instance_id}")
        return self.pods[instance_id]

    def _log(self, event: str, detail: str) -> None:
        self.event_log.append({"ts": datetime.now(timezone.utc).isoformat(), "event": event, "detail": detail})
