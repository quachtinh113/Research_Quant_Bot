"""
Abstract base pod.

A pod owns exactly one symbol, one order ledger and one circuit breaker. It
runs as an independent asyncio worker consuming a bar feed. On every closed
bar the pod:

  1. asserts the history it received contains nothing after the bar close,
  2. marks to market,
  3. enforces the Central Risk Engine's hard stop / take profit,
  4. applies the drawdown ladder (Tier 2 -> DRAINING_POSITIONS -> breaker),
  5. flattens if draining,
  6. runs alpha (regime + signal) and asks the risk engine for a size,
  7. executes through the CCXT gateway if, and only if, RUNNING and allowed,
  8. emits one Section IV telemetry payload.

Alpha code (subclasses) never sees the risk engine's internals and cannot
set its own size, stop or breaker state.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, List, Optional

import pandas as pd

from orchestration.constants import (
    ExitReason,
    OrderSide,
    OrderType,
    PodStatus,
    SignalDirection,
    TimeInForce,
)
from orchestration.builder_core.feed.arctic_store import parse_interval
from orchestration.builder_core.feed.bar_feed import Bar, BarEvent, assert_no_lookahead
from orchestration.builder_core.execution.ccxt_gateway import CCXTExecutionGateway, ExecutionResult
from orchestration.builder_core.execution.order_manager import OrderManager, TradeRecord
from orchestration.mentor_core.persistence.state_store import StateStore
from orchestration.mentor_core.risk_engine.central_risk import CentralRiskEngine, PositionSizingResult
from orchestration.mentor_core.circuit_breakers.circuit_breaker import CircuitBreakerTier
from orchestration.schemas import (
    ChartMarkerSchema,
    DashboardTelemetrySchema,
    ExecutionPayloadSchema,
    InstitutionalTelemetryPayload,
    RegimeSchema,
    RiskParametersSchema,
    SignalSchema,
)
from orchestration.mentor_core.telemetry.dispatcher import TelemetryDispatcher

logger = logging.getLogger(__name__)

BarHook = Callable[["BasePod", InstitutionalTelemetryPayload], Awaitable[None]]


class BasePod(ABC):
    def __init__(
        self,
        instance_id: str,
        symbol: str,
        initial_equity: float = 100_000.0,
        risk_engine: Optional[CentralRiskEngine] = None,
        execution_gateway: Optional[CCXTExecutionGateway] = None,
        telemetry_dispatcher: Optional[TelemetryDispatcher] = None,
        state_store: Optional[StateStore] = None,
        atr_period: int = 14,
        bar_interval: str = "5min",
        allow_pyramiding: bool = False,
    ) -> None:
        self.instance_id = instance_id
        self.symbol = symbol
        self.status = PodStatus.INITIALIZING
        self.risk_engine = risk_engine or CentralRiskEngine()
        self.execution_gateway = execution_gateway or CCXTExecutionGateway()
        self.telemetry_dispatcher = telemetry_dispatcher or TelemetryDispatcher()
        self.order_manager = OrderManager(pod_id=instance_id, initial_equity=initial_equity)
        self.state_store = state_store
        self.atr_period = atr_period
        self.bar_interval = parse_interval(bar_interval)
        self.allow_pyramiding = allow_pyramiding

        self.hrp_portfolio_weight: float = 1.0  # set by the orchestrator
        self.last_telemetry: Optional[InstitutionalTelemetryPayload] = None
        self.last_bar: Optional[Bar] = None
        self.last_bar_wall_time: Optional[float] = None
        self.bars_processed = 0
        self.last_bar_return = 0.0
        self.breaker_reason: Optional[str] = None
        self._drain_reason: Optional[str] = None
        self._drain_to_breaker = False
        self._stop_requested = False
        self._events: List[str] = []
        self._worker: Optional[asyncio.Task] = None

        if self.state_store is not None:
            saved = self.state_store.load_state(self.instance_id)
            if saved:
                self.order_manager.restore(saved)
                logger.info("Pod %s restored persisted state.", instance_id)

    # ============================================================ lifecycle
    def start(self) -> None:
        if self.status in (PodStatus.INITIALIZING, PodStatus.PAUSED):
            self.status = PodStatus.RUNNING
            self._stop_requested = False

    def pause(self) -> None:
        if self.status in (PodStatus.RUNNING, PodStatus.INITIALIZING):
            self.status = PodStatus.PAUSED

    def resume(self) -> None:
        if self.status == PodStatus.PAUSED:
            self.status = PodStatus.RUNNING

    def stop(self) -> None:
        """Request a graceful stop: the worker flattens and exits on the next bar."""
        self._stop_requested = True

    def trigger_circuit_breaker(self, reason: str) -> None:
        """Enter the drain path; status becomes CIRCUIT_BREAKER_TRIGGERED once flat."""
        if self.status == PodStatus.STOPPED:
            return
        self.breaker_reason = reason
        self.risk_engine.circuit_breaker.engage_kill_switch(reason)
        self._drain_to_breaker = True
        self._drain_reason = reason
        if self.order_manager.has_position(self.symbol):
            self.status = PodStatus.DRAINING_POSITIONS
        else:
            self.status = PodStatus.CIRCUIT_BREAKER_TRIGGERED

    def drain_positions(self, reason: str = "operator drain") -> None:
        if self.status == PodStatus.STOPPED:
            return
        self._drain_reason = reason
        self.status = PodStatus.DRAINING_POSITIONS

    def release_circuit_breaker(self) -> None:
        """Operator override only. Clears the kill switch; drawdown gating still applies."""
        self.risk_engine.circuit_breaker.release_kill_switch()
        self.breaker_reason = None
        self._drain_to_breaker = False
        if self.status == PodStatus.CIRCUIT_BREAKER_TRIGGERED:
            self.status = PodStatus.PAUSED

    @property
    def worker_alive(self) -> bool:
        return self._worker is not None and not self._worker.done()

    # ========================================================= alpha roles
    @abstractmethod
    def detect_regime(self, history_df: pd.DataFrame) -> RegimeSchema: ...

    @abstractmethod
    def generate_signal(self, history_df: pd.DataFrame, current_bar: Bar) -> SignalSchema: ...

    @abstractmethod
    def build_execution_payload(
        self, signal: SignalSchema, risk_result: PositionSizingResult, current_bar: Bar
    ) -> ExecutionPayloadSchema: ...

    @abstractmethod
    def formulate_thesis(
        self, regime: RegimeSchema, signal: SignalSchema, risk_result: PositionSizingResult
    ) -> str: ...

    # ======================================================== risk bridge
    def evaluate_risk(self, price: float, atr: float, signal: SignalSchema) -> PositionSizingResult:
        return self.risk_engine.evaluate_order(
            equity=self.order_manager.current_equity,
            price=price,
            atr=atr,
            direction=signal.direction,
            current_drawdown_pct=self.order_manager.current_drawdown_pct,
            pod_id=self.instance_id,
        )

    def _sync_ledger(self) -> None:
        if self.risk_engine.ledger is not None:
            self.risk_engine.ledger.set_exposure(self.instance_id, self.order_manager.gross_notional)

    async def _close_position(self, price: float, reason: ExitReason, bar: Bar) -> Optional[TradeRecord]:
        pos = self.order_manager.positions.get(self.symbol)
        if pos is None:
            return None
        res = await self.execution_gateway.execute_order(
            symbol=self.symbol,
            side=pos.side.opposite,
            order_type=OrderType.MARKET,
            target_price=price,
            amount=pos.amount,
            time_in_force=TimeInForce.IOC,
            max_slippage_bps=10_000,  # exits are never blocked by slippage tolerance
        )
        if not res.success:
            logger.error("Pod %s failed to close position: %s", self.instance_id, res.error_message)
            self._events.append(f"CLOSE_FAILED:{res.error_message}")
            return None
        record = self.order_manager.record_fill(res, reason=reason, timestamp=bar.timestamp.isoformat())
        if record is not None:
            self.risk_engine.circuit_breaker.register_trade_result(record.pnl_pct_equity)
            self._events.append(f"{reason.value}@{record.exit_price:.4f} pnl={record.pnl:.2f}")
        self._sync_ledger()
        return record

    async def flatten_now(self, reason: ExitReason = ExitReason.MANUAL) -> Optional[TradeRecord]:
        """Immediate flatten at the last known price (used by stop_pod / global breaker)."""
        if self.last_bar is None or not self.order_manager.has_position(self.symbol):
            return None
        return await self._close_position(self.last_bar.close, reason, self.last_bar)

    # ============================================================== on_bar
    async def on_bar(self, current_bar: Bar, history_df: pd.DataFrame) -> InstitutionalTelemetryPayload:
        assert_no_lookahead(history_df, current_bar.timestamp)
        if self.status == PodStatus.INITIALIZING:
            self.status = PodStatus.RUNNING
        self._events = []
        markers: List[ChartMarkerSchema] = []
        ts_unix = int(current_bar.timestamp.timestamp())

        # 2. mark to market
        self.order_manager.mark_to_market(self.symbol, current_bar.close)
        self.last_bar = current_bar

        # 3. hard stop / take profit (deterministic, before any alpha)
        pos = self.order_manager.positions.get(self.symbol)
        if pos is not None:
            stop_event = self.risk_engine.check_hard_stop(
                pos.side, pos.stop_loss, pos.take_profit, current_bar.open, current_bar.high, current_bar.low
            )
            if stop_event is not None:
                rec = await self._close_position(stop_event.exit_price, stop_event.reason, current_bar)
                if rec is not None:
                    markers.append(self.telemetry_dispatcher.create_event_marker(
                        ts_unix, stop_event.reason, f"{stop_event.reason.value} @ {rec.exit_price:.2f}"
                    ))

        # 4. drawdown ladder
        tier, forced_status, reason = self.risk_engine.drawdown_action(self.order_manager.current_drawdown_pct)
        if forced_status == PodStatus.DRAINING_POSITIONS and self.status in (PodStatus.RUNNING, PodStatus.PAUSED):
            self.breaker_reason = reason
            self._drain_to_breaker = True
            self._drain_reason = reason
            self.status = PodStatus.DRAINING_POSITIONS
            markers.append(self.telemetry_dispatcher.create_event_marker(ts_unix, "CIRCUIT_BREAKER", "TIER-2 BREAKER"))
            self._events.append(f"BREAKER:{reason}")

        # 5. drain
        if self.status == PodStatus.DRAINING_POSITIONS or self._stop_requested:
            if self.order_manager.has_position(self.symbol):
                rec = await self._close_position(current_bar.close, ExitReason.DRAIN, current_bar)
                if rec is not None:
                    markers.append(self.telemetry_dispatcher.create_event_marker(ts_unix, ExitReason.DRAIN, "DRAIN"))
            if not self.order_manager.has_position(self.symbol):
                if self._stop_requested:
                    self.status = PodStatus.STOPPED
                elif self._drain_to_breaker:
                    self.status = PodStatus.CIRCUIT_BREAKER_TRIGGERED
                elif self.status == PodStatus.DRAINING_POSITIONS:
                    self.status = PodStatus.PAUSED

        # 6. alpha + central risk
        regime = self.detect_regime(history_df)
        signal = self.generate_signal(history_df, current_bar)
        atr = self._calculate_atr(history_df, self.atr_period)
        risk_result = self.evaluate_risk(current_bar.close, atr, signal)
        exec_payload = self.build_execution_payload(signal, risk_result, current_bar)

        # 7. execution (RUNNING only)
        if self.status == PodStatus.RUNNING and risk_result.allowed and signal.direction != SignalDirection.NEUTRAL:
            await self._maybe_enter(signal, risk_result, exec_payload, current_bar, markers, ts_unix)
        elif signal.direction != SignalDirection.NEUTRAL and self.status != PodStatus.RUNNING:
            self._events.append(f"SIGNAL_SUPPRESSED:{self.status.value}")

        # bookkeeping
        self.order_manager.mark_to_market(self.symbol, current_bar.close)
        self._sync_ledger()
        self.last_bar_return = self.order_manager.end_of_bar()
        self.bars_processed += 1
        self.last_bar_wall_time = time.monotonic()

        # 8. telemetry
        telemetry = self._build_telemetry(current_bar, regime, signal, risk_result, exec_payload, markers, tier)
        self.last_telemetry = telemetry
        await self.telemetry_dispatcher.dispatch(telemetry)
        if self.state_store is not None:
            try:
                self.state_store.save_state(self.instance_id, self.order_manager.snapshot())
            except Exception as exc:  # persistence must never stop trading
                logger.warning("Pod %s state save failed: %s", self.instance_id, exc)
        return telemetry

    async def _maybe_enter(
        self,
        signal: SignalSchema,
        risk_result: PositionSizingResult,
        exec_payload: ExecutionPayloadSchema,
        bar: Bar,
        markers: List[ChartMarkerSchema],
        ts_unix: int,
    ) -> None:
        pos = self.order_manager.positions.get(self.symbol)
        if pos is not None:
            if pos.side == exec_payload.side:
                if not self.allow_pyramiding:
                    self._events.append("SKIP:position_already_open")
                    return
            else:
                await self._close_position(bar.close, ExitReason.SIGNAL_FLIP, bar)
                markers.append(self.telemetry_dispatcher.create_event_marker(ts_unix, ExitReason.SIGNAL_FLIP, "FLIP"))
                # Re-size after the flip because equity changed.
                risk_result = self.evaluate_risk(bar.close, self._last_atr, signal)
                if not risk_result.allowed:
                    self._events.append(f"ENTRY_REJECTED:{risk_result.rejection_reason}")
                    return

        # The amount is the risk engine's number, never the pod's.
        amount = min(exec_payload.amount, risk_result.units) if exec_payload.amount > 0 else risk_result.units
        res: ExecutionResult = await self.execution_gateway.execute_order(
            symbol=self.symbol,
            side=exec_payload.side,
            order_type=exec_payload.order_type,
            target_price=exec_payload.price,
            amount=amount,
            time_in_force=exec_payload.params.timeInForce,
            max_slippage_bps=exec_payload.params.max_slippage_bps,
        )
        if res.success:
            self.order_manager.record_fill(
                res, stop_loss=risk_result.stop_loss_price, take_profit=risk_result.take_profit_price,
                timestamp=bar.timestamp.isoformat(),
            )
            self._sync_ledger()
            markers.append(self.telemetry_dispatcher.create_marker(
                ts_unix, signal.direction, f"{signal.direction.value} @ {res.executed_price:.2f}"
            ))
            self._events.append(f"ENTRY:{signal.direction.value}@{res.executed_price:.4f} x{res.executed_amount:.6f}")
        else:
            self._events.append(f"ENTRY_REJECTED:{res.error_message}")

    # ============================================================ telemetry
    def _build_telemetry(
        self,
        bar: Bar,
        regime: RegimeSchema,
        signal: SignalSchema,
        risk_result: PositionSizingResult,
        exec_payload: ExecutionPayloadSchema,
        markers: List[ChartMarkerSchema],
        tier: CircuitBreakerTier,
    ) -> InstitutionalTelemetryPayload:
        om = self.order_manager
        pos = om.positions.get(self.symbol)
        eq = om.current_equity
        unrealized_pct = (pos.unrealized_pnl / eq * 100.0) if pos and eq > 0 else 0.0
        tp1 = risk_result.take_profit_price
        tp2 = round(tp1 * (1.01 if signal.direction == SignalDirection.BUY else 0.99), 8) if tp1 > 0 else 0.0
        thesis = self.formulate_thesis(regime, signal, risk_result)
        if self._events:
            thesis += " Events: " + "; ".join(self._events)

        return InstitutionalTelemetryPayload(
            instance_id=self.instance_id,
            timestamp=bar.timestamp.isoformat(),
            symbol=self.symbol,
            status=self.status,
            regime=regime,
            signal=signal,
            risk_parameters=RiskParametersSchema(
                recommended_position_pct=round(risk_result.position_pct, 6),
                portfolio_hrp_weight=round(self.hrp_portfolio_weight, 6),
                entry_range=(round(bar.close * 0.998, 8), round(bar.close * 1.002, 8)),
                hard_stop_loss=risk_result.stop_loss_price,
                take_profit_targets=(tp1, tp2),
                risk_reward_ratio=risk_result.risk_reward_ratio,
                cvar_impact_pct=risk_result.cvar_impact_pct,
                risk_engine_reason=risk_result.rejection_reason,
            ),
            execution_payload=exec_payload,
            dashboard_telemetry=DashboardTelemetrySchema(
                live_pnl_usd=round(om.realized_pnl - om.fees_paid + (pos.unrealized_pnl if pos else 0.0), 2),
                unrealized_pnl_pct=round(unrealized_pct, 4),
                current_drawdown_pct=round(om.current_drawdown_pct * 100.0, 4),
                margin_utilization_pct=round(om.margin_utilization_pct, 4),
                equity_usd=round(eq, 2),
                open_position=pos.to_dict() if pos else None,
                circuit_breaker_tier=tier.value,
                chart_markers=markers,
            ),
            analytical_thesis=thesis,
        )

    # =============================================================== worker
    async def run(
        self,
        feed: Any,
        pace_seconds: float = 0.0,
        after_bar: Optional[BarHook] = None,
    ) -> None:
        """Independent worker loop. ``feed`` must expose ``stream(pace_seconds)``."""
        self._worker = asyncio.current_task()
        self.start()
        try:
            async for event in feed.stream(pace_seconds):
                if self.status == PodStatus.STOPPED:
                    break
                telemetry = await self.on_bar(event.bar, event.history)
                if after_bar is not None:
                    await after_bar(self, telemetry)
                if self.status == PodStatus.STOPPED:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Pod %s worker crashed: %s", self.instance_id, exc)
            self.trigger_circuit_breaker(f"worker exception: {exc}")
            raise

    # =============================================================== health
    def health(self) -> Dict[str, Any]:
        om = self.order_manager
        return {
            "instance_id": self.instance_id,
            "symbol": self.symbol,
            "status": self.status,
            "worker_alive": self.worker_alive,
            "equity_usd": round(om.current_equity, 2),
            "drawdown_pct": round(om.current_drawdown_pct * 100.0, 4),
            "gross_notional_usd": round(om.gross_notional, 2),
            "last_bar_time": self.last_bar.timestamp.isoformat() if self.last_bar else None,
            "bars_processed": self.bars_processed,
            "circuit_breaker_tier": self.risk_engine.circuit_breaker.tier.value,
            "hrp_weight": round(self.hrp_portfolio_weight, 6),
        }

    # ================================================================ utils
    _last_atr: float = 0.0

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        if df.empty:
            self._last_atr = 1.0
            return 1.0
        if len(df) < period + 1:
            self._last_atr = float(df["close"].iloc[-1] * 0.01)
            return self._last_atr
        high, low = df["high"], df["low"]
        prev_close = df["close"].shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]
        self._last_atr = float(atr) if pd.notna(atr) and atr > 0 else float(df["close"].iloc[-1] * 0.01)
        return self._last_atr
