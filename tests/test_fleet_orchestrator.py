"""
Fleet orchestrator: concurrent pod workers, lifecycle controls, health
checks, aggregated exposure and the global drawdown kill-switch.
"""

import asyncio

import pytest

from orchestration.constants import PodStatus
from orchestration.data.bar_feed import BarFeed
from orchestration.fleet_orchestrator import FleetOrchestrator
from orchestration.pod.sample_pod import VolatilityBreakoutPod
from orchestration.risk.central_risk import CentralRiskEngine, RiskLimits
from orchestration.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from tests.conftest import make_breakout_then_crash, make_ohlcv


def _pods(equity=100_000.0, lenient=False):
    def engine():
        if not lenient:
            return CentralRiskEngine(RiskLimits(0.01, 2.0, 3.0, 0.50))
        return CentralRiskEngine(RiskLimits(0.01, 2.0, 3.0, 0.50), circuit_breaker=CircuitBreaker(CircuitBreakerConfig(0.30, 0.60, 0.9, 99)))

    p1 = VolatilityBreakoutPod("POD_BTC", "BTC/USDT", lookback_period=10, initial_equity=equity, risk_engine=engine())
    p2 = VolatilityBreakoutPod("POD_ETH", "ETH/USDT", lookback_period=10, initial_equity=equity, risk_engine=engine())
    return p1, p2


def test_two_concurrent_pod_workers():
    async def _run():
        orch = FleetOrchestrator(total_fund_equity=200_000.0, rebalance_every_bars=5)
        p1, p2 = _pods()
        orch.register_pod(p1)
        orch.register_pod(p2)
        assert p1.hrp_portfolio_weight == pytest.approx(0.5)
        assert p1.risk_engine.ledger is orch.ledger and p2.risk_engine.ledger is orch.ledger

        feeds = {
            "POD_BTC": BarFeed("BTC/USDT", make_ohlcv(40, base=50_000.0, drift=25.0, vol=60.0, seed=1)),
            "POD_ETH": BarFeed("ETH/USDT", make_ohlcv(40, base=2_500.0, drift=1.0, vol=5.0, seed=2)),
        }
        await orch.run(feeds)

        assert p1.bars_processed == 40 and p2.bars_processed == 40
        assert len(orch.pod_returns["POD_BTC"]) == 40
        report = orch.health_check()
        assert report.total_registered_pods == 2 and report.active_pods == 2
        assert report.global_circuit_breaker is False
        assert report.pod_statuses == {"POD_BTC": PodStatus.RUNNING, "POD_ETH": PodStatus.RUNNING}
        assert sum(report.pod_weights.values()) == pytest.approx(1.0)
        assert all(not p.worker_alive for p in report.pods)
        exposure = orch.aggregate_exposure()
        assert exposure["gross_notional_usd"] == pytest.approx(p1.order_manager.gross_notional + p2.order_manager.gross_notional, abs=1.0)
        assert exposure["gross_leverage"] <= orch.max_total_leverage
        summary = orch.get_fleet_status_summary()
        assert summary["pod_statuses"]["POD_BTC"] == "RUNNING"
        await orch.shutdown()
        assert p1.status == PodStatus.STOPPED

    asyncio.run(_run())


def test_pause_resume_stop_lifecycle():
    async def _run():
        orch = FleetOrchestrator(total_fund_equity=200_000.0)
        p1, _ = _pods()
        orch.register_pod(p1)
        df = make_breakout_then_crash(quiet_bars=16, crash_open=102.0, after_bars=2)  # breakout without a real crash
        feed = BarFeed("BTC/USDT", df)

        # Pause before the breakout bar: the signal must be suppressed.
        orch.pause_pod("POD_BTC")
        assert p1.status == PodStatus.PAUSED
        for _ in range(17):
            ev = feed.next_event()
            t = await orch.step_pod("POD_BTC", ev.bar, ev.history)
        assert t.signal.direction.value == "BUY" and t.status == PodStatus.PAUSED
        assert not p1.order_manager.has_position("BTC/USDT")
        assert "SIGNAL_SUPPRESSED" in t.analytical_thesis

        orch.resume_pod("POD_BTC")
        assert p1.status == PodStatus.RUNNING
        ev = feed.next_event()
        await orch.step_pod("POD_BTC", ev.bar, ev.history)

        # Start a worker on the remaining bars and stop it: STOPPED and flat.
        task = orch.start_pod("POD_BTC", feed)
        await asyncio.sleep(0)
        await orch.stop_pod("POD_BTC")
        assert task.done() and p1.status == PodStatus.STOPPED
        assert not p1.order_manager.has_position("BTC/USDT")
        with pytest.raises(KeyError):
            orch.start_pod("POD_UNKNOWN", feed)

    asyncio.run(_run())


def test_global_circuit_breaker_on_fund_drawdown():
    async def _run():
        orch = FleetOrchestrator(total_fund_equity=200_000.0, max_fund_drawdown_pct=0.10)
        p1, p2 = _pods(lenient=True)  # pod-level breakers will not fire; only the fund-level one
        orch.register_pod(p1)
        orch.register_pod(p2)
        feeds = {
            "POD_BTC": BarFeed("BTC/USDT", make_breakout_then_crash(16, 100.0, 103.0, 80.0, 4)),
            "POD_ETH": BarFeed("ETH/USDT", make_breakout_then_crash(16, 100.0, 103.0, 80.0, 4)),
        }
        await orch.run(feeds)

        assert orch.is_global_circuit_breaker_triggered is True
        assert "fund drawdown" in orch.global_breaker_reason.lower()
        assert orch.fund_drawdown_pct >= 0.10
        for pod in (p1, p2):
            assert pod.status == PodStatus.CIRCUIT_BREAKER_TRIGGERED
            assert not pod.order_manager.has_position(pod.symbol)
            assert pod.order_manager.realized_pnl < 0
        assert orch.ledger.gross_notional == pytest.approx(0.0)
        report = orch.health_check()
        assert report.active_pods == 0 and report.global_circuit_breaker

        with pytest.raises(RuntimeError):
            orch.start_pod("POD_BTC", feeds["POD_BTC"])
        with pytest.raises(RuntimeError):
            orch.resume_pod("POD_BTC")

        # Operator release: pods return to PAUSED, never straight to RUNNING.
        orch.release_global_circuit_breaker()
        assert orch.is_global_circuit_breaker_triggered is False
        assert p1.status == PodStatus.PAUSED and p2.status == PodStatus.PAUSED
        assert any(e["event"] == "global_breaker" for e in orch.event_log)

    asyncio.run(_run())


def test_hrp_rebalance_uses_pod_returns():
    async def _run():
        orch = FleetOrchestrator(total_fund_equity=200_000.0, rebalance_every_bars=1)
        p1, p2 = _pods()
        orch.register_pod(p1)
        orch.register_pod(p2)
        feeds = {
            "POD_BTC": BarFeed("BTC/USDT", make_ohlcv(60, base=50_000.0, drift=40.0, vol=200.0, seed=11)),
            "POD_ETH": BarFeed("ETH/USDT", make_ohlcv(60, base=2_500.0, drift=0.5, vol=2.0, seed=12)),
        }
        await orch.run(feeds)
        w = {pid: p.hrp_portfolio_weight for pid, p in orch.pods.items()}
        assert sum(w.values()) == pytest.approx(1.0)
        assert all(0.0 <= v <= 1.0 for v in w.values())

    asyncio.run(_run())
