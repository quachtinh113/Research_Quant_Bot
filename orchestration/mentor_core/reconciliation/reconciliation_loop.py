"""
Exchange reconciliation for live pods.

Compares the pod's internal position with the exchange's reported position
and corrects internal state toward the exchange (the exchange is the source
of truth for what is actually held).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from orchestration.constants import OrderSide

logger = logging.getLogger(__name__)


async def reconcile_once(pod) -> Dict[str, Any]:
    gateway = pod.execution_gateway
    if not gateway.is_live or gateway.exchange is None:
        return {"skipped": True, "reason": "paper mode"}

    await gateway.rate_limiter.acquire()
    positions = await gateway.exchange.fetch_positions([pod.symbol])
    external_qty = 0.0
    external_entry: Optional[float] = None
    for p in positions or []:
        if p.get("symbol") == pod.symbol:
            contracts = float(p.get("contracts") or p.get("amount") or 0.0)
            side = (p.get("side") or "").lower()
            external_qty = -contracts if side == "short" else contracts
            external_entry = p.get("entryPrice")
            break

    internal_pos = pod.order_manager.positions.get(pod.symbol)
    internal_qty = 0.0
    if internal_pos is not None:
        internal_qty = internal_pos.amount if internal_pos.side == OrderSide.BUY else -internal_pos.amount

    drift = external_qty - internal_qty
    if abs(drift) <= 1e-8:
        return {"skipped": False, "drift": 0.0}

    logger.warning(
        "Reconciliation drift for pod %s: internal %s vs exchange %s", pod.instance_id, internal_qty, external_qty
    )
    if abs(external_qty) <= 1e-12:
        pod.order_manager.positions.pop(pod.symbol, None)
    else:
        side = OrderSide.BUY if external_qty > 0 else OrderSide.SELL
        price = float(external_entry or (pod.last_bar.close if pod.last_bar else 0.0))
        if internal_pos is not None and internal_pos.side == side:
            internal_pos.amount = abs(external_qty)
        else:
            from orchestration.builder_core.execution.order_manager import Position
            pod.order_manager.positions[pod.symbol] = Position(
                symbol=pod.symbol, side=side, amount=abs(external_qty), entry_price=price,
                current_price=price, stop_loss=0.0, take_profit=0.0,
            )
    if pod.last_bar is not None:
        pod.order_manager.mark_to_market(pod.symbol, pod.last_bar.close)
    if pod.state_store is not None:
        pod.state_store.save_state(pod.instance_id, pod.order_manager.snapshot())
    return {"skipped": False, "drift": drift, "internal": internal_qty, "external": external_qty}


async def run_reconciliation(pod, interval_seconds: float = 30.0, stop_event: Optional[asyncio.Event] = None) -> None:
    while stop_event is None or not stop_event.is_set():
        await asyncio.sleep(interval_seconds)
        try:
            await reconcile_once(pod)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Reconciliation error for pod %s: %s", pod.instance_id, exc)
