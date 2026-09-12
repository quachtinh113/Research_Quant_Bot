"""
Section IV telemetry schema conformance, marker formatting, OpenAlgo mapping
and dispatcher sinks.
"""

import asyncio
import json

import pytest
from pydantic import ValidationError

from orchestration.config import TelemetrySettings
from orchestration.constants import (
    MarketRegime,
    OrderSide,
    OrderType,
    PodStatus,
    SignalDirection,
    TimeInForce,
    VolatilityState,
)
from orchestration.data.bar_feed import BarFeed
from orchestration.pod.sample_pod import VolatilityBreakoutPod
from orchestration.schemas import (
    MANDATED_TOP_LEVEL_FIELDS,
    ChartMarkerSchema,
    DashboardTelemetrySchema,
    ExecutionParamsSchema,
    ExecutionPayloadSchema,
    InstitutionalTelemetryPayload,
    RegimeSchema,
    RiskParametersSchema,
    SignalSchema,
    TelemetryPayload,
)
from orchestration.telemetry.dispatcher import TelemetryDispatcher
from tests.conftest import make_ohlcv


def _payload(**overrides) -> InstitutionalTelemetryPayload:
    base = dict(
        instance_id="POD_XAUUSD_M5_BREAKOUT",
        timestamp="2026-03-01T00:05:00+00:00",
        symbol="XAU/USD",
        status=PodStatus.RUNNING,
        regime=RegimeSchema(
            type=MarketRegime.TRENDING_BULL,
            volatility_state=VolatilityState.NORMAL,
            liquidity_assessment="Institutional liquidity depth verified.",
        ),
        signal=SignalSchema(direction=SignalDirection.BUY, confidence_score=0.85, primary_factors=["DONCHIAN_BREAKOUT"]),
        risk_parameters=RiskParametersSchema(
            recommended_position_pct=0.25,
            portfolio_hrp_weight=0.33,
            entry_range=(2050.0, 2052.0),
            hard_stop_loss=2040.0,
            take_profit_targets=(2070.0, 2085.0),
            risk_reward_ratio=2.0,
            cvar_impact_pct=1.45,
        ),
        execution_payload=ExecutionPayloadSchema(
            order_type=OrderType.LIMIT, side=OrderSide.BUY, price=2051.0, amount=1.5,
            params=ExecutionParamsSchema(timeInForce=TimeInForce.GTC, max_slippage_bps=5),
        ),
        dashboard_telemetry=DashboardTelemetrySchema(
            live_pnl_usd=1250.50, unrealized_pnl_pct=1.25, current_drawdown_pct=0.85, margin_utilization_pct=35.0,
            chart_markers=[ChartMarkerSchema(time=1700000000, position="belowBar", color="green", shape="arrowUp", text="BUY @ 2051.00")],
        ),
        analytical_thesis="Breakout confirmed via multi-horizon momentum.",
    )
    base.update(overrides)
    return InstitutionalTelemetryPayload(**base)


def test_telemetry_schema_validation_and_roundtrip():
    payload = _payload()
    data = json.loads(payload.model_dump_json())
    assert data["instance_id"] == "POD_XAUUSD_M5_BREAKOUT"
    assert data["execution_payload"]["exchange_standard"] == "CCXT"
    assert data["status"] == "RUNNING"
    assert data["regime"]["type"] == "TRENDING_BULL"
    assert data["signal"]["confidence_score"] == 0.85
    assert data["dashboard_telemetry"]["chart_markers"][0]["shape"] == "arrowUp"
    assert TelemetryPayload is InstitutionalTelemetryPayload
    assert InstitutionalTelemetryPayload.model_validate_json(payload.model_dump_json()) == payload


def test_mandated_top_level_fields_exact():
    data = json.loads(_payload().model_dump_json())
    assert tuple(data.keys()) == MANDATED_TOP_LEVEL_FIELDS


def test_schema_rejects_invalid_values():
    with pytest.raises(ValidationError):
        SignalSchema(direction=SignalDirection.BUY, confidence_score=1.5, primary_factors=[])
    with pytest.raises(ValidationError):
        _payload(status="BROKEN")
    with pytest.raises(ValidationError):
        _payload(regime=RegimeSchema(type="SIDEWAYS", volatility_state=VolatilityState.LOW, liquidity_assessment="x"))
    with pytest.raises(ValidationError):  # side must match signal
        _payload(execution_payload=ExecutionPayloadSchema(order_type=OrderType.MARKET, side=OrderSide.SELL, price=1.0, amount=1.0))
    with pytest.raises(ValidationError):  # extra fields forbidden
        InstitutionalTelemetryPayload(**{**_payload().model_dump(), "llm_override": True})
    with pytest.raises(ValidationError):
        ChartMarkerSchema(time=1, position="middle", color="red", shape="arrowUp", text="x")
    with pytest.raises(ValidationError):
        _payload(timestamp="not-a-date")


def test_marker_formatting():
    d = TelemetryDispatcher()
    buy = d.create_marker(1700000000, SignalDirection.BUY, "BUY")
    sell = d.create_marker(1700000001, SignalDirection.SELL, "SELL")
    assert (buy.shape, buy.position) == ("arrowUp", "belowBar")
    assert (sell.shape, sell.position) == ("arrowDown", "aboveBar")
    stop = d.create_event_marker(1700000002, "HARD_STOP", "stop")
    assert stop.shape == "square" and stop.position == "aboveBar"


def test_openalgo_order_mapping():
    d = TelemetryDispatcher(TelemetrySettings(openalgo_api_key="k", openalgo_strategy="AFQ", openalgo_exchange="CRYPTO"))
    req = d.to_openalgo_order(_payload())
    body = req.model_dump()
    assert body["symbol"] == "XAUUSD" and body["action"] == "BUY"
    assert body["pricetype"] == "LIMIT" and body["price"] == 2051.0 and body["quantity"] == 1.5
    assert body["strategy"] == "AFQ:POD_XAUUSD_M5_BREAKOUT" and body["apikey"] == "k"
    neutral = _payload(
        signal=SignalSchema(direction=SignalDirection.NEUTRAL, confidence_score=0.0, primary_factors=[]),
        execution_payload=ExecutionPayloadSchema(order_type=OrderType.LIMIT, side=OrderSide.BUY, price=1.0, amount=0.0),
    )
    assert d.to_openalgo_order(neutral) is None


def test_dispatcher_sinks(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    received = []
    d = TelemetryDispatcher(TelemetrySettings(jsonl_path=path), on_payload_emitted=received.append)
    out = asyncio.run(d.dispatch(_payload()))
    assert json.loads(out)["symbol"] == "XAU/USD"
    assert len(received) == 1 and len(d.payload_history) == 1
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1 and InstitutionalTelemetryPayload.model_validate_json(lines[0])
    assert d.tradingview_markers()[0]["shape"] == "arrowUp"


def test_pod_emits_valid_payload_every_bar():
    df = make_ohlcv(40, base=1000.0, drift=1.5, vol=2.0)
    feed = BarFeed("BTC/USDT", df)
    pod = VolatilityBreakoutPod("SCHEMA_POD", "BTC/USDT", lookback_period=10)

    async def _run():
        await pod.run(feed)

    asyncio.run(_run())
    history = pod.telemetry_dispatcher.payload_history
    assert len(history) == 40
    for p in history:
        raw = p.model_dump_json()
        parsed = InstitutionalTelemetryPayload.model_validate_json(raw)
        assert tuple(json.loads(raw).keys()) == MANDATED_TOP_LEVEL_FIELDS
        assert parsed.instance_id == "SCHEMA_POD" and parsed.symbol == "BTC/USDT"
        assert parsed.dashboard_telemetry.current_drawdown_pct >= 0.0
