"""
quant-server: MCP tools over the orchestration package for the dual-agent
workspace (quant-builder / quant-mentor).

Every tool is a plain function registered with FastMCP so it can be unit
tested without a transport. Heavy libraries are imported inside the tool
that needs them, so the server starts in well under a second.

Run (stdio):  python mcp/quant_server/server.py
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("QUANT_REPO_ROOT") or Path(__file__).resolve().parents[2]).resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REVIEWS_PATH = ROOT / "mcp" / "reviews.jsonl"
TELEMETRY_PATH = ROOT / "logs" / "fleet_telemetry.jsonl"
DATA_STORE = ROOT / "data_store"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================ read tools
def risk_size_position(
    equity: float,
    price: float,
    atr: float,
    direction: str,
    max_risk_pct: float = 0.01,
    atr_stop_mult: float = 2.0,
    atr_tp_mult: float = 3.0,
    max_gross_exposure_pct: float = 0.5,
    current_drawdown_pct: float = 0.0,
) -> Dict[str, Any]:
    """Deterministic Central Risk Engine sizing: min(Equity*RiskPct/(k*ATR), MaxGross*Equity/Price)."""
    from orchestration.constants import SignalDirection
    from orchestration.risk.central_risk import CentralRiskEngine, RiskLimits

    engine = CentralRiskEngine(RiskLimits(max_risk_pct, atr_stop_mult, atr_tp_mult, max_gross_exposure_pct))
    res = engine.evaluate_order(equity, price, atr, SignalDirection(direction.upper()), current_drawdown_pct)
    return {
        "allowed": res.allowed,
        "units": res.units,
        "notional_value": res.notional_value,
        "position_pct": res.position_pct,
        "stop_loss_price": res.stop_loss_price,
        "take_profit_price": res.take_profit_price,
        "risk_reward_ratio": res.risk_reward_ratio,
        "cvar_impact_pct": res.cvar_impact_pct,
        "breaker_tier": res.breaker_tier.value,
        "rejection_reason": res.rejection_reason,
    }


def risk_check_hard_stop(
    side: str, stop_loss: float, take_profit: float, bar_open: float, bar_high: float, bar_low: float
) -> Dict[str, Any]:
    """Test a closed bar against a k x ATR stop / target. Gaps fill at the bar open."""
    from orchestration.constants import OrderSide
    from orchestration.risk.central_risk import CentralRiskEngine

    ev = CentralRiskEngine().check_hard_stop(OrderSide(side.lower()), stop_loss, take_profit, bar_open, bar_high, bar_low)
    if ev is None:
        return {"triggered": False}
    return {"triggered": True, "reason": ev.reason.value, "exit_price": ev.exit_price}


def portfolio_hrp_weights(returns: Dict[str, List[float]], method: str = "HRP", max_weight: float = 1.0) -> Dict[str, Any]:
    """HRP or CVaR weights (Riskfolio-Lib when installed, native Lopez de Prado otherwise)."""
    import pandas as pd

    from orchestration.risk.portfolio_hrp import PortfolioOptimizer

    opt = PortfolioOptimizer(method=method, max_weight=max_weight)
    w = opt.optimize_weights(pd.DataFrame(returns))
    return {"weights": w, "engine": opt.last_engine, "sum": sum(w.values())}


def pit_list_symbols(library: str = "live_simulation") -> Dict[str, Any]:
    """Symbols held in a point-in-time library (ArcticDB or Parquet fallback)."""
    from orchestration.data.arctic_store import PointInTimeStore

    store = PointInTimeStore(uri=f"lmdb://{DATA_STORE.as_posix()}", library_name=library, fallback_dir=DATA_STORE)
    return {"library": library, "backend": store.backend_type, "symbols": store.list_symbols()}


def pit_read_as_of(symbol: str, as_of: str, lookback_bars: int = 100, library: str = "live_simulation") -> Dict[str, Any]:
    """Bars whose close time is <= as_of. Never returns a future bar."""
    import pandas as pd

    from orchestration.data.arctic_store import PointInTimeStore

    store = PointInTimeStore(uri=f"lmdb://{DATA_STORE.as_posix()}", library_name=library, fallback_dir=DATA_STORE)
    df = store.read_as_of(symbol, pd.Timestamp(as_of), lookback_bars=lookback_bars)
    rows = [{"timestamp": ts.isoformat(), **{k: float(v) for k, v in r.items()}} for ts, r in df.iterrows()]
    return {"symbol": symbol, "as_of": as_of, "backend": store.backend_type, "rows": len(rows), "bars": rows}


def telemetry_tail(n: int = 20, instance_id: Optional[str] = None) -> Dict[str, Any]:
    """Last n Section IV telemetry payloads written by the fleet."""
    if not TELEMETRY_PATH.exists():
        return {"path": str(TELEMETRY_PATH), "payloads": []}
    out: List[dict] = []
    with open(TELEMETRY_PATH, encoding="utf-8") as fh:
        for line in fh:
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            if instance_id and p.get("instance_id") != instance_id:
                continue
            out.append(p)
    return {"path": str(TELEMETRY_PATH), "payloads": out[-n:]}


def review_recall(bot: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """Recall mentor verdicts recorded with review_log."""
    if not REVIEWS_PATH.exists():
        return {"reviews": []}
    rows = [json.loads(l) for l in REVIEWS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    if bot:
        rows = [r for r in rows if r.get("bot") == bot]
    return {"reviews": rows[-limit:]}


# =========================================================== build tools
def paper_simulation(
    symbol: str = "BTC/USDT",
    bars: int = 80,
    lookback_period: int = 12,
    initial_equity: float = 100_000.0,
    base_price: float = 65_000.0,
    drift_pct: float = 0.001,
    vol_pct: float = 0.0025,
    seed: int = 42,
) -> Dict[str, Any]:
    """Replay one VolatilityBreakoutPod in paper mode on synthetic bars and return the ledger summary."""
    import asyncio

    import numpy as np
    import pandas as pd

    from orchestration.data.bar_feed import BarFeed
    from orchestration.pod.sample_pod import VolatilityBreakoutPod

    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01 00:05", periods=bars, freq="5min", tz="UTC")
    close = base_price + np.cumsum(rng.normal(drift_pct, vol_pct, bars) * base_price)
    df = pd.DataFrame({
        "open": np.concatenate([[base_price], close[:-1]]),
        "high": close + rng.uniform(0.0005, 0.002, bars) * base_price,
        "low": close - rng.uniform(0.0005, 0.002, bars) * base_price,
        "close": close,
        "volume": rng.uniform(10, 150, bars),
    }, index=idx)
    pod = VolatilityBreakoutPod("MCP_SIM", symbol, lookback_period=lookback_period, initial_equity=initial_equity)

    async def _run():
        await pod.run(BarFeed(symbol, df))

    asyncio.run(_run())
    om = pod.order_manager
    return {
        "instance_id": pod.instance_id,
        "status": pod.status.value,
        "bars": pod.bars_processed,
        "fills": sum(1 for t in om.trade_history if t.success),
        "closed_trades": len(om.closed_trades),
        "realized_pnl": round(om.realized_pnl, 2),
        "fees_paid": round(om.fees_paid, 2),
        "final_equity": round(om.current_equity, 2),
        "max_drawdown_pct": round(max((max(om.equity_curve[: i + 1]) - v) / max(om.equity_curve[: i + 1]) for i, v in enumerate(om.equity_curve)) * 100, 4),
        "breaker_tier": pod.risk_engine.circuit_breaker.tier.value,
    }


def ma_cross_sweep(
    closes: List[float],
    fast_windows: List[int],
    slow_windows: List[int],
    fees_bps: float = 6.0,
    periods_per_year: int = 105_120,
) -> Dict[str, Any]:
    """
    Declared-grid moving-average cross sweep. Uses vectorbt when importable,
    otherwise a pandas implementation with identical semantics. Reports the
    whole population (trial count, median, quantiles); never picks a winner.
    """
    import numpy as np
    import pandas as pd

    price = pd.Series(closes, dtype=float)
    grid = [(f, s) for f in fast_windows for s in slow_windows if f < s]
    results = []
    engine = "pandas"
    try:
        import vectorbt as vbt  # type: ignore

        for f, s in grid:
            fast, slow = price.rolling(f).mean(), price.rolling(s).mean()
            entries, exits = (fast > slow) & (fast.shift(1) <= slow.shift(1)), (fast < slow) & (fast.shift(1) >= slow.shift(1))
            pf = vbt.Portfolio.from_signals(price, entries.fillna(False), exits.fillna(False), fees=fees_bps / 10_000.0, freq="5min")
            results.append({"fast": f, "slow": s, "total_return": float(pf.total_return()), "sharpe": float(pf.sharpe_ratio()), "trades": int(pf.trades.count())})
        engine = "vectorbt"
    except Exception:
        results = []
        for f, s in grid:
            fast, slow = price.rolling(f).mean(), price.rolling(s).mean()
            pos = (fast > slow).astype(float).shift(1).fillna(0.0)  # act on next bar
            rets = price.pct_change().fillna(0.0)
            turns = pos.diff().abs().fillna(pos.iloc[0])
            strat = pos * rets - turns * fees_bps / 10_000.0
            eq = (1 + strat).cumprod()
            sd = strat.std()
            results.append({
                "fast": f, "slow": s,
                "total_return": float(eq.iloc[-1] - 1),
                "sharpe": float(strat.mean() / sd * math.sqrt(periods_per_year)) if sd > 0 else 0.0,
                "trades": int(turns.sum()),
            })
    sharpes = np.array([r["sharpe"] for r in results]) if results else np.array([0.0])
    return {
        "engine": engine,
        "n_trials": len(results),
        "population": {
            "sharpe_median": float(np.median(sharpes)),
            "sharpe_q25": float(np.quantile(sharpes, 0.25)),
            "sharpe_q75": float(np.quantile(sharpes, 0.75)),
            "share_positive": float((sharpes > 0).mean()),
        },
        "cells": results,
        "note": "Feed n_trials to audit_deflated_sharpe before believing any single cell.",
    }


def openalgo_build_order(
    symbol: str, action: str, quantity: float, pricetype: str = "MARKET", price: float = 0.0,
    strategy: str = "AgentFundQuant", exchange: str = "CRYPTO", product: str = "MIS",
) -> Dict[str, Any]:
    """Build (do NOT send) an OpenAlgo /api/v1/placeorder body. Sending orders is outside MCP by design."""
    from orchestration.schemas import OpenAlgoOrderRequest

    req = OpenAlgoOrderRequest(
        apikey="<set-at-dispatch>", strategy=strategy, symbol=symbol.replace("/", ""), action=action.upper(),
        exchange=exchange, pricetype=pricetype.upper(), product=product, quantity=quantity, price=price,
    )
    return {"endpoint": "POST {openalgo_host}/api/v1/placeorder", "body": req.model_dump(), "sent": False}


# =========================================================== audit tools
def audit_deflated_sharpe(
    observed_sharpe: float, n_trials: int, n_obs: int, skew: float = 0.0, kurt: float = 3.0, sharpe_std: Optional[float] = None
) -> Dict[str, Any]:
    """
    Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014). Sharpe inputs are per
    observation (not annualised). Returns the expected max Sharpe under the
    null across n_trials and the probability the observed Sharpe beats it.
    """
    from math import erf, sqrt

    euler = 0.5772156649
    if n_trials < 1 or n_obs < 3:
        return {"error": "n_trials >= 1 and n_obs >= 3 required"}
    var = (sharpe_std ** 2) if sharpe_std else 1.0 / n_obs

    def _z(p: float) -> float:  # inverse normal, Acklam approximation
        a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
        b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01]
        c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
        d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
        plow = 0.02425
        if p < plow:
            q = sqrt(-2 * math.log(p))
            return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
        if p > 1 - plow:
            q = sqrt(-2 * math.log(1 - p))
            return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)

    if n_trials == 1:
        sr0 = 0.0
    else:
        sr0 = sqrt(var) * ((1 - euler) * _z(1 - 1.0 / n_trials) + euler * _z(1 - 1.0 / (n_trials * math.e)))
    denom = sqrt(max(1e-12, 1 - skew * observed_sharpe + (kurt - 1) / 4.0 * observed_sharpe ** 2))
    stat = (observed_sharpe - sr0) * sqrt(n_obs - 1) / denom
    psr = 0.5 * (1 + erf(stat / sqrt(2)))
    return {
        "observed_sharpe": observed_sharpe,
        "expected_max_sharpe_under_null": sr0,
        "deflated_sharpe_probability": psr,
        "verdict": "PASS" if psr >= 0.95 else "FAIL",
        "threshold": 0.95,
        "n_trials": n_trials,
        "n_obs": n_obs,
    }


LOOKAHEAD_PATTERNS = [
    (r"\.shift\(\s*-\s*\d+", "negative shift pulls future rows into the present"),
    (r"center\s*=\s*True", "centred rolling window uses future bars"),
    (r"\.bfill\(|method\s*=\s*['\"]bfill['\"]", "backfill copies future values backwards"),
    (r"iloc\[\s*i\s*\+\s*1", "explicit next-row indexing"),
    (r"\.max\(\)\s*$|\.min\(\)\s*$", "full-sample max/min may include future rows (verify)"),
    (r"fit\(\s*(X|df|data)\s*\)", "estimator fitted on full sample (verify train-only fit)"),
    (r"resample\([^)]*label\s*=\s*['\"]right['\"]", "right-labelled resample can stamp bars with future close"),
]


def audit_lookahead_scan(path: str, max_findings: int = 200) -> Dict[str, Any]:
    """Static scan of a Python file or directory for common look-ahead constructs. Findings need human confirmation."""
    target = (ROOT / path) if not Path(path).is_absolute() else Path(path)
    if not target.exists():
        return {"error": f"{target} does not exist"}
    files = [target] if target.is_file() else sorted(p for p in target.rglob("*.py") if "__pycache__" not in p.parts)
    findings = []
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for pat, why in LOOKAHEAD_PATTERNS:
                if re.search(pat, line):
                    findings.append({"file": str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f), "line": i, "code": line.strip()[:160], "pattern": pat, "why": why})
                    if len(findings) >= max_findings:
                        break
    return {"scanned_files": len(files), "findings": findings, "count": len(findings)}


def review_log(bot: str, phase: str, verdict: str, notes: str, evidence: Optional[Dict[str, Any]] = None, reviewer: str = "quant-mentor") -> Dict[str, Any]:
    """Append a mentor verdict (met / not_evidence_yet / fail / info) to mcp/reviews.jsonl."""
    allowed = {"met", "not_evidence_yet", "fail", "info"}
    if verdict not in allowed:
        return {"error": f"verdict must be one of {sorted(allowed)}"}
    REVIEWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": _utcnow(), "bot": bot, "phase": phase, "verdict": verdict, "notes": notes, "evidence": evidence or {}, "reviewer": reviewer}
    with open(REVIEWS_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return {"recorded": True, "path": str(REVIEWS_PATH), "row": row}


TOOLS = {
    "read": [risk_size_position, risk_check_hard_stop, portfolio_hrp_weights, pit_list_symbols, pit_read_as_of, telemetry_tail, review_recall],
    "build": [paper_simulation, ma_cross_sweep, openalgo_build_order],
    "audit": [audit_deflated_sharpe, audit_lookahead_scan, review_log],
}


def build_server():
    try:  # mcp >= 2.0
        from mcp.server.mcpserver import MCPServer as _Server
    except ImportError:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP as _Server

    server = _Server("quant-server", instructions="Deterministic quant tools over the Agent_Fund_Quant orchestration package. No tool sends live orders.")
    for group in TOOLS.values():
        for fn in group:
            server.tool()(fn)
    return server


if __name__ == "__main__":
    build_server().run()
