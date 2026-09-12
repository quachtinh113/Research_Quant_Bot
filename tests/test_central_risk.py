"""
Central Risk Engine: deterministic sizing, hard stops, two-tier breakers,
drawdown kill-switch, fleet exposure ledger and HRP allocation.
"""

import asyncio

import numpy as np
import pandas as pd
import pytest

from orchestration.constants import ExitReason, OrderSide, PodStatus, SignalDirection
from orchestration.data.bar_feed import BarFeed
from orchestration.pod.sample_pod import VolatilityBreakoutPod
from orchestration.risk.central_risk import CentralRiskEngine, ExposureLedger, RiskLimits
from orchestration.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerTier
from orchestration.risk.portfolio_hrp import PortfolioOptimizer
from tests.conftest import make_breakout_then_crash


# ---------------------------------------------------------------- sizing
def test_deterministic_position_sizing():
    engine = CentralRiskEngine(RiskLimits(0.01, 2.0, 3.0, 0.50))
    # risk = 1,000; stop_dist = 50 -> 20 units -> 40,000 notional (< 50,000 cap)
    res = engine.evaluate_order(equity=100_000.0, price=2_000.0, atr=25.0, direction=SignalDirection.BUY)
    assert res.allowed
    assert res.units == pytest.approx(20.0)
    assert res.notional_value == pytest.approx(40_000.0)
    assert res.stop_loss_price == pytest.approx(1_950.0)
    assert res.take_profit_price == pytest.approx(2_075.0)
    assert res.risk_reward_ratio == pytest.approx(1.5)
    assert res.risk_pct_applied == pytest.approx(0.01)

    short = engine.evaluate_order(100_000.0, 2_000.0, 25.0, SignalDirection.SELL)
    assert short.stop_loss_price == pytest.approx(2_050.0)
    assert short.take_profit_price == pytest.approx(1_925.0)


def test_exposure_capping():
    engine = CentralRiskEngine(RiskLimits(0.05, 1.0, 2.0, 0.20))
    # uncapped: 5,000 / 2 = 2,500 units = 250,000 notional; cap = 20,000 -> 200 units
    res = engine.evaluate_order(100_000.0, 100.0, 2.0, SignalDirection.BUY)
    assert res.allowed
    assert res.notional_value == pytest.approx(20_000.0)
    assert res.units == pytest.approx(200.0)
    assert res.position_pct == pytest.approx(0.20)


def test_alpha_cannot_inflate_size():
    """No input other than equity/price/ATR/direction changes the number."""
    engine = CentralRiskEngine(RiskLimits(0.01, 2.0, 3.0, 0.50))
    a = engine.size_position(100_000.0, 100.0, 1.0, SignalDirection.BUY)
    b = engine.size_position(100_000.0, 100.0, 1.0, SignalDirection.BUY, risk_pct=0.10)  # asks for 10x
    assert a.units == pytest.approx(b.units) == pytest.approx(500.0)
    c = engine.size_position(100_000.0, 100.0, 1.0, SignalDirection.BUY, risk_pct=0.005)  # may lower
    assert c.units == pytest.approx(250.0)
    assert engine.evaluate_order(100_000.0, 100.0, 1.0, SignalDirection.NEUTRAL).allowed is False
    assert engine.evaluate_order(100_000.0, 0.0, 1.0, SignalDirection.BUY).allowed is False


def test_tier1_halves_risk_and_tier2_blocks():
    cb = CircuitBreaker(CircuitBreakerConfig(0.04, 0.08))
    engine = CentralRiskEngine(RiskLimits(0.01, 2.0, 3.0, 5.0), circuit_breaker=cb)
    normal = engine.evaluate_order(100_000.0, 100.0, 1.0, SignalDirection.BUY, current_drawdown_pct=0.01)
    soft = engine.evaluate_order(100_000.0, 100.0, 1.0, SignalDirection.BUY, current_drawdown_pct=0.05)
    hard = engine.evaluate_order(100_000.0, 100.0, 1.0, SignalDirection.BUY, current_drawdown_pct=0.09)
    assert normal.units == pytest.approx(500.0)
    assert soft.units == pytest.approx(250.0) and soft.breaker_tier == CircuitBreakerTier.TIER_1_SOFT_LIMIT
    assert hard.allowed is False and hard.breaker_tier == CircuitBreakerTier.TIER_2_HARD_STOP
    assert "Tier 2" in hard.rejection_reason


# -------------------------------------------------------------- breakers
def test_two_tier_circuit_breaker():
    cb = CircuitBreaker(CircuitBreakerConfig(max_drawdown_soft_pct=0.04, max_drawdown_hard_pct=0.08))
    cb.update_drawdown(0.02)
    assert cb.evaluate()[0] == CircuitBreakerTier.NORMAL
    cb.update_drawdown(0.05)
    assert cb.evaluate()[0] == CircuitBreakerTier.TIER_1_SOFT_LIMIT
    cb.update_drawdown(0.09)
    assert cb.evaluate()[0] == CircuitBreakerTier.TIER_2_HARD_STOP


def test_daily_loss_and_streak_and_kill_switch():
    cb = CircuitBreaker(CircuitBreakerConfig(max_daily_loss_pct=0.03, max_consecutive_losses=3))
    for _ in range(3):
        cb.register_trade_result(-0.005)
    assert cb.evaluate()[0] == CircuitBreakerTier.TIER_1_SOFT_LIMIT  # streak
    cb.register_trade_result(-0.02)  # cumulative -3.5% today
    assert cb.evaluate()[0] == CircuitBreakerTier.TIER_2_HARD_STOP
    cb.reset_daily()
    cb.register_trade_result(0.01)
    assert cb.evaluate()[0] == CircuitBreakerTier.NORMAL
    cb.engage_kill_switch("operator")
    assert cb.evaluate()[0] == CircuitBreakerTier.TIER_2_HARD_STOP
    cb.release_kill_switch()
    assert cb.evaluate()[0] == CircuitBreakerTier.NORMAL
    with pytest.raises(ValueError):
        CircuitBreakerConfig(max_drawdown_soft_pct=0.1, max_drawdown_hard_pct=0.05)


# ------------------------------------------------------------ hard stops
def test_hard_stop_detection_and_gap_fill():
    engine = CentralRiskEngine()
    # long, stop 95, tp 110
    assert engine.check_hard_stop(OrderSide.BUY, 95.0, 110.0, 100.0, 101.0, 96.0) is None
    ev = engine.check_hard_stop(OrderSide.BUY, 95.0, 110.0, 99.0, 100.0, 94.0)
    assert ev.reason == ExitReason.HARD_STOP and ev.exit_price == pytest.approx(95.0)
    gap = engine.check_hard_stop(OrderSide.BUY, 95.0, 110.0, 80.0, 81.0, 78.0)  # gapped through
    assert gap.reason == ExitReason.HARD_STOP and gap.exit_price == pytest.approx(80.0)
    tp = engine.check_hard_stop(OrderSide.BUY, 95.0, 110.0, 105.0, 112.0, 104.0)
    assert tp.reason == ExitReason.TAKE_PROFIT and tp.exit_price == pytest.approx(110.0)
    # stop beats target when both touched
    both = engine.check_hard_stop(OrderSide.BUY, 95.0, 110.0, 100.0, 115.0, 90.0)
    assert both.reason == ExitReason.HARD_STOP
    # short, stop 105, tp 90
    sh = engine.check_hard_stop(OrderSide.SELL, 105.0, 90.0, 100.0, 106.0, 99.0)
    assert sh.reason == ExitReason.HARD_STOP and sh.exit_price == pytest.approx(105.0)


def test_drawdown_kill_switch_drains_pod_and_blocks_new_risk():
    """Breakout entry -> gap crash through the k x ATR stop -> Tier 2 -> drain -> breaker."""
    df = make_breakout_then_crash(quiet_bars=16)
    feed = BarFeed("BTC/USDT", df)
    engine = CentralRiskEngine(
        RiskLimits(0.01, 2.0, 3.0, 0.50),
        circuit_breaker=CircuitBreaker(CircuitBreakerConfig(0.05, 0.08, 0.50, 50)),
    )
    pod = VolatilityBreakoutPod("KILL_POD", "BTC/USDT", lookback_period=10, initial_equity=100_000.0, risk_engine=engine)
    statuses = []

    async def _run():
        async for ev in feed.stream():
            t = await pod.on_bar(ev.bar, ev.history)
            statuses.append((ev.bar.close, t.status, pod.order_manager.has_position("BTC/USDT")))

    asyncio.run(_run())

    breakout_close, breakout_status, had_pos = statuses[16]
    assert breakout_close == 103.0 and breakout_status == PodStatus.RUNNING and had_pos is True
    pos_notional = pod.order_manager.trade_history[0].cost
    assert pos_notional == pytest.approx(50_000.0, rel=0.01)  # capped at 50% gross exposure

    crash_close, crash_status, has_pos = statuses[17]
    assert has_pos is False
    assert crash_status == PodStatus.CIRCUIT_BREAKER_TRIGGERED
    assert pod.order_manager.closed_trades[0].reason == ExitReason.HARD_STOP
    assert pod.order_manager.closed_trades[0].exit_price == pytest.approx(80.0 * (1 - 0.0003), rel=1e-3)
    assert pod.order_manager.current_drawdown_pct >= 0.08
    assert engine.circuit_breaker.tier == CircuitBreakerTier.TIER_2_HARD_STOP

    # After the breaker: every later bar stays flat and the status is sticky.
    for _, st, hp in statuses[18:]:
        assert st == PodStatus.CIRCUIT_BREAKER_TRIGGERED and hp is False
    assert pod.last_telemetry.risk_parameters.risk_engine_reason is not None


# ------------------------------------------------------------- ledger
def test_exposure_ledger_caps_fleet_gross_notional():
    ledger = ExposureLedger(max_gross_notional=100_000.0)
    ledger.set_exposure("POD_A", 80_000.0)
    engine_b = CentralRiskEngine(RiskLimits(0.05, 1.0, 2.0, 5.0), ledger=ledger)
    res = engine_b.evaluate_order(100_000.0, 100.0, 1.0, SignalDirection.BUY, pod_id="POD_B")
    assert res.allowed and res.notional_value == pytest.approx(20_000.0)
    ledger.set_exposure("POD_B", 20_000.0)
    assert ledger.headroom("POD_C") == pytest.approx(0.0)
    blocked = engine_b.evaluate_order(100_000.0, 100.0, 1.0, SignalDirection.BUY, pod_id="POD_C")
    assert blocked.allowed is False and "exposure cap" in blocked.rejection_reason.lower()
    assert ledger.leverage(fund_equity=200_000.0) == pytest.approx(0.5)


# ---------------------------------------------------------------- HRP
def _returns_panel(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    low_vol = rng.normal(0.0002, 0.002, n)
    high_vol = rng.normal(0.0002, 0.02, n)
    corr_high = 0.9 * high_vol + rng.normal(0.0, 0.005, n)
    return pd.DataFrame({"LOW_VOL": low_vol, "HIGH_VOL": high_vol, "CORR_HIGH": corr_high})


@pytest.mark.parametrize("method", ["HRP", "CVaR"])
def test_hrp_weights_sum_to_one_and_favour_low_risk(method):
    opt = PortfolioOptimizer(method=method)
    w = opt.optimize_weights(_returns_panel())
    assert set(w) == {"LOW_VOL", "HIGH_VOL", "CORR_HIGH"}
    assert sum(w.values()) == pytest.approx(1.0)
    assert all(v >= 0 for v in w.values())
    assert w["LOW_VOL"] > w["HIGH_VOL"] and w["LOW_VOL"] > w["CORR_HIGH"]
    assert opt.last_engine in ("riskfolio", "native")


def test_hrp_weight_bounds_and_degenerate_inputs():
    opt = PortfolioOptimizer(method="HRP", max_weight=0.5)
    w = opt.optimize_weights(_returns_panel())
    assert max(w.values()) <= 0.5 + 1e-9 and sum(w.values()) == pytest.approx(1.0)
    assert opt.optimize_weights(pd.DataFrame()) == {}
    assert opt.optimize_weights(pd.DataFrame({"ONLY": [0.1, 0.2, 0.3]})) == {"ONLY": 1.0}
