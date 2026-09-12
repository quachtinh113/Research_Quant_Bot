"""
End-to-end fleet simulation.

Phase 1  Two pods (BTC/USDT, ETH/USDT) run as concurrent asyncio workers on
         independent point-in-time feeds, executing paper orders through the
         CCXT gateway and emitting Section IV telemetry every bar.
Phase 2  A stress feed (breakout, then a gap crash) is replayed. Pod-level
         hard stops and Tier-2 breakers fire, the fund-level drawdown limit
         engages the global circuit breaker, and every pod ends flat in
         CIRCUIT_BREAKER_TRIGGERED.

Run:  python run_live_simulation.py
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from orchestration.config import ExecutionSettings, RiskSettings, TelemetrySettings
from orchestration.constants import ExecutionMode, PodStatus
from orchestration.data.arctic_store import PointInTimeStore
from orchestration.data.bar_feed import BarFeed
from orchestration.execution.ccxt_gateway import CCXTExecutionGateway, MarketRules
from orchestration.fleet_orchestrator import FleetOrchestrator
from orchestration.pod.sample_pod import VolatilityBreakoutPod
from orchestration.risk.central_risk import CentralRiskEngine
from orchestration.telemetry.dispatcher import TelemetryDispatcher

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

OUT_DIR = Path(__file__).parent / "logs"
OUT_DIR.mkdir(exist_ok=True)
TELEMETRY_PATH = OUT_DIR / "fleet_telemetry.jsonl"
STORE_DIR = Path(__file__).parent / "data_store"


# ----------------------------------------------------------------- data
def trending_market(symbol: str, bars: int, base: float, drift_pct: float, vol_pct: float, seed: int,
                    start: str = "2026-03-01 00:05:00") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=bars, freq="5min", tz="UTC")
    steps = rng.normal(drift_pct, vol_pct, bars) * base
    close = base + np.cumsum(steps)
    high = close + rng.uniform(0.0005, 0.002, bars) * base
    low = close - rng.uniform(0.0005, 0.002, bars) * base
    open_p = np.concatenate([[base], close[:-1]])
    volume = rng.uniform(10.0, 150.0, bars)
    return pd.DataFrame({"open": open_p, "high": high, "low": low, "close": close, "volume": volume}, index=dates)


def stress_market(last_close: float, start: pd.Timestamp, quiet_bars: int = 18, crash_pct: float = 0.22) -> pd.DataFrame:
    """Tight range -> breakout bar -> gap crash -> quiet aftermath (deterministic)."""
    rows = []
    for i in range(quiet_bars):
        c = last_close * (1 + 0.0005 * ((-1) ** i))
        rows.append((c * 0.9995, c * 1.001, c * 0.999, c, 50.0))
    breakout = last_close * 1.03
    rows.append((last_close, breakout * 1.001, last_close * 0.999, breakout, 150.0))
    crash_open = breakout * (1 - crash_pct)
    rows.append((crash_open, crash_open * 1.01, crash_open * 0.98, crash_open * 0.995, 500.0))
    for i in range(6):
        c = crash_open * 0.995 * (1 + 0.0005 * ((-1) ** i))
        rows.append((c * 0.9995, c * 1.001, c * 0.999, c, 60.0))
    dates = pd.date_range(start + pd.Timedelta("5min"), periods=len(rows), freq="5min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=dates)


# ----------------------------------------------------------------- pods
def build_pod(instance_id: str, symbol: str, equity: float, rules: MarketRules) -> VolatilityBreakoutPod:
    risk = CentralRiskEngine(settings=RiskSettings(
        max_risk_per_trade_pct=0.01, atr_multiplier_stop=2.0, atr_multiplier_tp=3.0,
        max_gross_exposure_pct=0.50, max_drawdown_soft_pct=0.05, max_drawdown_hard_pct=0.08,
        max_daily_loss_pct=0.20, max_consecutive_losses=5,
    ))
    gateway = CCXTExecutionGateway(
        exchange_id="binance", mode=ExecutionMode.PAPER,
        settings=ExecutionSettings(taker_fee_bps=6.0, maker_fee_bps=2.0, sim_market_slippage_bps=3.0),
        market_rules={symbol: rules},
    )
    telemetry = TelemetryDispatcher(TelemetrySettings(jsonl_path=TELEMETRY_PATH))
    return VolatilityBreakoutPod(
        instance_id=instance_id, symbol=symbol, lookback_period=12, initial_equity=equity,
        risk_engine=risk, execution_gateway=gateway, telemetry_dispatcher=telemetry, bar_interval="5min",
    )


def banner(title: str) -> None:
    print("\n" + "=" * 88 + f"\n{title}\n" + "=" * 88)


def print_health(orch: FleetOrchestrator) -> None:
    r = orch.health_check()
    print(f"fund equity {r.total_fund_equity:,.2f} | peak {r.peak_fund_equity:,.2f} | fund DD {r.fund_drawdown_pct:.2f}% "
          f"| gross notional {r.gross_notional_usd:,.2f} | leverage {r.gross_leverage:.3f}x "
          f"| global breaker {r.global_circuit_breaker}")
    for p in r.pods:
        print(f"  {p.instance_id:<14} {p.status.value:<26} eq {p.equity_usd:>12,.2f}  dd {p.drawdown_pct:>6.2f}%  "
              f"notional {p.gross_notional_usd:>12,.2f}  bars {p.bars_processed:>3}  tier {p.circuit_breaker_tier}  "
              f"hrp {p.hrp_weight:.3f}")


async def main() -> None:
    if TELEMETRY_PATH.exists():
        TELEMETRY_PATH.unlink()

    banner("INSTITUTIONAL MULTI-BOT ORCHESTRATION ENGINE  |  PAPER MODE")
    orch = FleetOrchestrator(total_fund_equity=1_000_000.0, max_fund_drawdown_pct=0.10, max_total_leverage=2.0,
                             rebalance_every_bars=10)
    btc = build_pod("POD_BTCUSDT_M5", "BTC/USDT", 500_000.0, MarketRules(2, 5, 0.00001, None, 5.0))
    eth = build_pod("POD_ETHUSDT_M5", "ETH/USDT", 500_000.0, MarketRules(2, 4, 0.0001, None, 5.0))
    orch.register_pod(btc)
    orch.register_pod(eth)
    print(f"registered pods: {list(orch.pods)}  initial HRP weights: "
          f"{ {k: round(v.hrp_portfolio_weight, 3) for k, v in orch.pods.items()} }")
    print(f"fleet exposure ledger cap: {orch.ledger.max_gross_notional:,.0f} USD gross notional")

    # ---------------------------------------------------------- phase 1
    banner("PHASE 1  |  two concurrent pod workers on point-in-time feeds (60 bars each)")
    store = PointInTimeStore(library_name="live_simulation", fallback_dir=STORE_DIR)
    df_btc = trending_market("BTC/USDT", 60, 65_000.0, drift_pct=0.0012, vol_pct=0.0025, seed=42)
    df_eth = trending_market("ETH/USDT", 60, 3_500.0, drift_pct=0.0008, vol_pct=0.0030, seed=88)
    store.write_bars("BTC/USDT", df_btc, prune_previous=True)
    store.write_bars("ETH/USDT", df_eth, prune_previous=True)
    print(f"point-in-time store backend: {store.backend_type}  symbols: {store.list_symbols()}")

    feeds = {
        "POD_BTCUSDT_M5": BarFeed.from_store(store, "BTC/USDT"),
        "POD_ETHUSDT_M5": BarFeed.from_store(store, "ETH/USDT"),
    }
    await orch.run(feeds)
    print_health(orch)
    for pod in (btc, eth):
        fills = [t for t in pod.order_manager.trade_history if t.success]
        print(f"  {pod.instance_id}: {len(fills)} paper fills, {len(pod.order_manager.closed_trades)} closed trades, "
              f"realised PnL {pod.order_manager.realized_pnl:,.2f}, fees {pod.order_manager.fees_paid:,.2f}")

    sample = next((p for p in reversed(btc.telemetry_dispatcher.payload_history)
                   if p.signal.direction.value != "NEUTRAL"), btc.last_telemetry)
    banner("SAMPLE SECTION IV TELEMETRY PAYLOAD (BTC pod, last non-neutral bar)")
    print(sample.model_dump_json(indent=2))
    markers = btc.telemetry_dispatcher.tradingview_markers()
    print(f"\nTradingView markers emitted for BTC pod: {len(markers)}  e.g. {markers[:2]}")
    oa = btc.telemetry_dispatcher.to_openalgo_order(sample)
    print(f"OpenAlgo /api/v1/placeorder body: {oa.model_dump() if oa else None}")

    # ---------------------------------------------------------- phase 2
    banner("PHASE 2  |  stress replay: breakout then 22% gap crash on both symbols")
    stress_feeds = {
        "POD_BTCUSDT_M5": BarFeed("BTC/USDT", stress_market(btc.last_bar.close, btc.last_bar.timestamp)),
        "POD_ETHUSDT_M5": BarFeed("ETH/USDT", stress_market(eth.last_bar.close, eth.last_bar.timestamp)),
    }
    await orch.run(stress_feeds)
    print_health(orch)
    print("\nfleet event log:")
    for e in orch.event_log:
        print(f"  {e['ts']}  {e['event']:<24} {e['detail']}")
    print("\nlast closed trades:")
    for pod in (btc, eth):
        for t in pod.order_manager.closed_trades[-2:]:
            print(f"  {pod.instance_id} {t.side.name:<4} {t.amount:.5f} @ {t.entry_price:,.2f} -> {t.exit_price:,.2f} "
                  f"pnl {t.pnl:,.2f} ({t.pnl_pct_equity*100:.2f}% eq) reason {t.reason.value}")
    print("\nlast BTC telemetry status / breaker tier / thesis:")
    lt = btc.last_telemetry
    print(f"  {lt.status.value} | {lt.dashboard_telemetry.circuit_breaker_tier} | {lt.analytical_thesis[:220]}")

    banner("FINAL FLEET STATUS (JSON)")
    summary = orch.get_fleet_status_summary()
    summary.pop("pods", None)
    print(json.dumps(summary, indent=2))
    n_lines = sum(1 for _ in open(TELEMETRY_PATH, encoding="utf-8"))
    print(f"\ntelemetry JSONL written: {TELEMETRY_PATH} ({n_lines} payloads)")
    all_cb = all(p.status == PodStatus.CIRCUIT_BREAKER_TRIGGERED for p in orch.pods.values())
    print(f"global circuit breaker engaged: {orch.is_global_circuit_breaker_triggered} | all pods drained + halted: {all_cb}")
    await orch.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
