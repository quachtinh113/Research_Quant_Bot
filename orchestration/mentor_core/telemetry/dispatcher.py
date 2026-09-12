"""
Telemetry dispatcher.

Serialises Section IV payloads and fans them out to:
  * an in-memory history (always),
  * an append-only JSONL file (optional),
  * a JSON webhook such as the OpenAlgo strategy webhook (optional),
  * a WebSocket broadcast for dashboards (optional),
and maps execution payloads to OpenAlgo ``/api/v1/placeorder`` requests.

Dispatch never raises: telemetry failures must not block the trading loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from orchestration.config import TelemetrySettings
from orchestration.constants import ExitReason, OrderType, SignalDirection
from orchestration.schemas import ChartMarkerSchema, InstitutionalTelemetryPayload, OpenAlgoOrderRequest

logger = logging.getLogger(__name__)

MARKER_STYLES: Dict[str, Dict[str, str]] = {
    "BUY": {"position": "belowBar", "color": "#26a69a", "shape": "arrowUp"},
    "SELL": {"position": "aboveBar", "color": "#ef5350", "shape": "arrowDown"},
    "NEUTRAL": {"position": "inBar", "color": "#90a4ae", "shape": "circle"},
    "HARD_STOP": {"position": "aboveBar", "color": "#b71c1c", "shape": "square"},
    "TAKE_PROFIT": {"position": "belowBar", "color": "#1b5e20", "shape": "square"},
    "SIGNAL_FLIP": {"position": "inBar", "color": "#ff9800", "shape": "circle"},
    "DRAIN": {"position": "aboveBar", "color": "#6a1b9a", "shape": "square"},
    "MANUAL": {"position": "inBar", "color": "#607d8b", "shape": "circle"},
    "CIRCUIT_BREAKER": {"position": "aboveBar", "color": "#000000", "shape": "square"},
}


class TelemetryDispatcher:
    def __init__(
        self,
        settings: Optional[TelemetrySettings] = None,
        on_payload_emitted: Optional[Callable[[InstitutionalTelemetryPayload], None]] = None,
        openalgo_webhook_url: Optional[str] = None,  # backwards compat
    ) -> None:
        self.settings = settings or TelemetrySettings()
        if openalgo_webhook_url:
            self.settings = self.settings.model_copy(update={"webhook_url": openalgo_webhook_url})
        self.on_payload_emitted = on_payload_emitted
        self.payload_history: List[InstitutionalTelemetryPayload] = []
        self.max_history = 10_000
        self.dispatch_errors = 0
        self._client = None
        self._ws_clients: Set[Any] = set()
        self._ws_server = None
        if self.settings.jsonl_path:
            Path(self.settings.jsonl_path).parent.mkdir(parents=True, exist_ok=True)

    @property
    def webhook_url(self) -> Optional[str]:
        return self.settings.webhook_url

    # -------------------------------------------------------------- markers
    def create_marker(self, time_unix: int, direction: SignalDirection, text: str) -> ChartMarkerSchema:
        style = MARKER_STYLES[direction.value]
        return ChartMarkerSchema(time=int(time_unix), text=text, **style)

    def create_event_marker(self, time_unix: int, event: str, text: str) -> ChartMarkerSchema:
        key = event.value if isinstance(event, ExitReason) else str(event)
        style = MARKER_STYLES.get(key, MARKER_STYLES["MANUAL"])
        return ChartMarkerSchema(time=int(time_unix), text=text, **style)

    def tradingview_markers(self, instance_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """All markers emitted so far, in lightweight-charts ``setMarkers`` form."""
        out: List[Dict[str, Any]] = []
        for p in self.payload_history:
            if instance_id and p.instance_id != instance_id:
                continue
            out.extend(m.model_dump() for m in p.dashboard_telemetry.chart_markers)
        out.sort(key=lambda m: m["time"])
        return out

    # ------------------------------------------------------------- OpenAlgo
    def to_openalgo_order(self, payload: InstitutionalTelemetryPayload) -> Optional[OpenAlgoOrderRequest]:
        ex = payload.execution_payload
        if ex.amount <= 0 or payload.signal.direction == SignalDirection.NEUTRAL:
            return None
        pricetype = "MARKET" if ex.order_type == OrderType.MARKET else "LIMIT"
        return OpenAlgoOrderRequest(
            apikey=self.settings.openalgo_api_key or "",
            strategy=f"{self.settings.openalgo_strategy}:{payload.instance_id}",
            symbol=payload.symbol.replace("/", ""),
            action="BUY" if ex.side.value == "buy" else "SELL",
            exchange=self.settings.openalgo_exchange,
            pricetype=pricetype,
            product=self.settings.openalgo_product,
            quantity=ex.amount,
            price=ex.price if pricetype == "LIMIT" else 0.0,
        )

    async def send_openalgo_order(self, order: OpenAlgoOrderRequest) -> Dict[str, Any]:
        if not self.settings.openalgo_host:
            return {"status": "skipped", "message": "openalgo_host not configured"}
        url = self.settings.openalgo_host.rstrip("/") + "/api/v1/placeorder"
        return await self._post_json(url, order.model_dump())

    # ------------------------------------------------------------- dispatch
    async def dispatch(self, payload: InstitutionalTelemetryPayload) -> str:
        self.payload_history.append(payload)
        if len(self.payload_history) > self.max_history:
            self.payload_history = self.payload_history[-self.max_history :]

        if self.on_payload_emitted:
            try:
                self.on_payload_emitted(payload)
            except Exception as exc:  # never block trading on a sink error
                self.dispatch_errors += 1
                logger.warning("on_payload_emitted raised: %s", exc)

        json_output = payload.model_dump_json()

        if self.settings.jsonl_path:
            try:
                with open(self.settings.jsonl_path, "a", encoding="utf-8") as fh:
                    fh.write(json_output + "\n")
            except OSError as exc:
                self.dispatch_errors += 1
                logger.warning("JSONL telemetry write failed: %s", exc)

        if self.settings.webhook_url:
            await self._post_json(self.settings.webhook_url, json.loads(json_output))

        if self._ws_clients:
            await self._broadcast(json_output)

        return json_output

    async def _post_json(self, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import httpx  # type: ignore

            if self._client is None:
                self._client = httpx.AsyncClient(timeout=self.settings.http_timeout_sec)
            resp = await self._client.post(url, json=body, headers={"Content-Type": "application/json"})
            try:
                data = resp.json()
            except ValueError:
                data = {"status": "error", "message": resp.text[:200]}
            if resp.status_code >= 400:
                self.dispatch_errors += 1
            return data
        except Exception as exc:
            self.dispatch_errors += 1
            logger.warning("Telemetry POST to %s failed: %s", url, exc)
            return {"status": "error", "message": str(exc)}

    # ------------------------------------------------------------ websocket
    async def start_ws_server(self) -> bool:
        if not self.settings.ws_host:
            return False
        try:
            import websockets  # type: ignore

            async def handler(ws):
                self._ws_clients.add(ws)
                try:
                    async for _ in ws:  # ignore inbound; broadcast-only channel
                        pass
                finally:
                    self._ws_clients.discard(ws)

            self._ws_server = await websockets.serve(handler, self.settings.ws_host, self.settings.ws_port)
            return True
        except Exception as exc:
            logger.warning("WebSocket telemetry server not started: %s", exc)
            return False

    async def _broadcast(self, message: str) -> None:
        dead = []
        for ws in list(self._ws_clients):
            try:
                await ws.send(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # pragma: no cover
                pass
            self._client = None
        if self._ws_server is not None:
            self._ws_server.close()
            try:
                await self._ws_server.wait_closed()
            except Exception:  # pragma: no cover
                pass
            self._ws_server = None
