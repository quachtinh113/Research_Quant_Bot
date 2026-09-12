# Deployment & Monitoring Playbook

## 1. Parity check

```python
import numpy as np
import pandas as pd


def parity_report(research_positions: pd.DataFrame,
                  production_positions: pd.DataFrame,
                  tolerance: float = 1e-6) -> dict:
    """Run the production code over the backtest window and diff the position series."""
    idx = research_positions.index.intersection(production_positions.index)
    cols = research_positions.columns.intersection(production_positions.columns)
    a = research_positions.loc[idx, cols]
    b = production_positions.loc[idx, cols]

    diff = (a - b).abs()
    worst = diff.stack().sort_values(ascending=False).head(20)

    return {
        "aligned_periods": len(idx),
        "missing_in_production": sorted(set(research_positions.index) - set(idx))[:10],
        "extra_in_production": sorted(set(production_positions.index) - set(idx))[:10],
        "missing_columns": sorted(set(research_positions.columns) - set(cols)),
        "max_abs_diff": float(diff.to_numpy().max()) if diff.size else 0.0,
        "periods_with_diff": int((diff > tolerance).any(axis=1).sum()),
        "worst_offenders": {f"{k[0]} {k[1]}": float(v) for k, v in worst.items()},
        "passed": bool(diff.to_numpy().max() <= tolerance) if diff.size else False,
    }
```

Do not proceed with `passed: False`. Investigate the worst offenders first; a single
misaligned timestamp usually explains the whole table.

## 2. Order state machine

```python
from __future__ import annotations
import enum
import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


class OrderState(enum.Enum):
    INTENDED = "intended"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNKNOWN = "unknown"          # never treat as flat


TERMINAL = {OrderState.FILLED, OrderState.CANCELLED,
            OrderState.REJECTED, OrderState.EXPIRED}

ALLOWED = {
    OrderState.INTENDED: {OrderState.SUBMITTED, OrderState.REJECTED},
    OrderState.SUBMITTED: {OrderState.ACKNOWLEDGED, OrderState.REJECTED,
                           OrderState.UNKNOWN},
    OrderState.ACKNOWLEDGED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED,
                              OrderState.CANCELLED, OrderState.EXPIRED,
                              OrderState.UNKNOWN},
    OrderState.PARTIALLY_FILLED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED,
                                  OrderState.CANCELLED, OrderState.EXPIRED,
                                  OrderState.UNKNOWN},
    OrderState.UNKNOWN: set(OrderState),
}


@dataclass
class ManagedOrder:
    symbol: str
    quantity: float
    order_type: str
    strategy_id: str
    decision_ts: float
    state: OrderState = OrderState.INTENDED
    filled_quantity: float = 0.0
    broker_id: Optional[str] = None
    history: list = field(default_factory=list)

    @property
    def idempotency_key(self) -> str:
        payload = json.dumps({"s": self.symbol, "q": self.quantity,
                              "t": self.order_type, "sid": self.strategy_id,
                              "ts": round(self.decision_ts, 3)}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:24]

    def transition(self, new: OrderState, **info) -> None:
        allowed = ALLOWED.get(self.state, set())
        if self.state in TERMINAL:
            raise ValueError(f"{self.state.value} is terminal; refusing {new.value}")
        if new not in allowed:
            raise ValueError(f"illegal transition {self.state.value} -> {new.value}")
        self.history.append({"from": self.state.value, "to": new.value,
                             "at": time.time(), **info})
        self.state = new

    def is_open(self) -> bool:
        return self.state not in TERMINAL
```

The idempotency key is derived from the decision, not from a random identifier, so a
retry after a network timeout produces the same key and the broker can deduplicate.

## 3. Reconciliation

```python
def reconcile(internal: dict, broker: dict, tolerance: float = 1e-6) -> dict:
    """Halt on any mismatch. Trading through a reconciliation break compounds it."""
    symbols = set(internal) | set(broker)
    breaks = {}
    for s in symbols:
        i, b = internal.get(s, 0.0), broker.get(s, 0.0)
        if abs(i - b) > tolerance:
            breaks[s] = {"internal": i, "broker": b, "diff": i - b}
    return {"clean": not breaks, "breaks": breaks,
            "action": "HALT" if breaks else "continue"}
```

## 4. Circuit breakers

```python
from dataclasses import dataclass
import time


@dataclass
class BreakerConfig:
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.15
    max_position_pct: float = 0.10
    max_gross_leverage: float = 2.0
    max_orders_per_minute: int = 30
    max_data_staleness_s: float = 120.0
    prediction_zscore_limit: float = 5.0


class CircuitBreakers:
    """Evaluated before every order. Tripping is sticky until a manual reset."""

    def __init__(self, config: BreakerConfig):
        self.cfg = config
        self.tripped: dict[str, str] = {}
        self._order_times: list[float] = []

    def reset(self, name: str | None = None) -> None:
        if name:
            self.tripped.pop(name, None)
        else:
            self.tripped.clear()

    def _trip(self, name: str, detail: str) -> None:
        self.tripped.setdefault(name, detail)

    def check(self, *, equity, day_start_equity, peak_equity, positions,
              last_data_ts, prediction_z=0.0) -> dict:
        now = time.time()
        c = self.cfg

        if day_start_equity and (equity / day_start_equity - 1) < -c.max_daily_loss_pct:
            self._trip("daily_loss", f"{equity / day_start_equity - 1:.2%}")
        if peak_equity and (equity / peak_equity - 1) < -c.max_drawdown_pct:
            self._trip("drawdown", f"{equity / peak_equity - 1:.2%}")

        gross = sum(abs(v) for v in positions.values())
        if equity and gross / equity > c.max_gross_leverage:
            self._trip("leverage", f"{gross / equity:.2f}x")
        for sym, val in positions.items():
            if equity and abs(val) / equity > c.max_position_pct:
                self._trip("position_limit", f"{sym} {abs(val) / equity:.2%}")

        self._order_times = [t for t in self._order_times if now - t < 60]
        if len(self._order_times) > c.max_orders_per_minute:
            self._trip("order_rate", f"{len(self._order_times)}/min")

        if now - last_data_ts > c.max_data_staleness_s:
            self._trip("stale_data", f"{now - last_data_ts:.0f}s")
        if abs(prediction_z) > c.prediction_zscore_limit:
            self._trip("model_extrapolation", f"z={prediction_z:.1f}")

        return {"can_trade": not self.tripped, "tripped": dict(self.tripped)}

    def record_order(self) -> None:
        self._order_times.append(time.time())
```

## 5. Drift detection

```python
import numpy as np
from scipy import stats


def psi(expected, actual, buckets: int = 10) -> float:
    """Population stability index. Above 0.25 warrants investigation."""
    edges = np.percentile(expected, np.linspace(0, 100, buckets + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, bins=edges)[0] / len(expected)
    a = np.histogram(actual, bins=edges)[0] / len(actual)
    e, a = np.clip(e, 1e-6, None), np.clip(a, 1e-6, None)
    return float(((a - e) * np.log(a / e)).sum())


def drift_report(train_features, live_features) -> dict:
    out = {}
    for col in train_features.columns:
        if col not in live_features:
            out[col] = {"status": "MISSING IN LIVE"}
            continue
        e = train_features[col].dropna().to_numpy()
        a = live_features[col].dropna().to_numpy()
        if len(a) < 30:
            out[col] = {"status": "insufficient live data"}
            continue
        ks = stats.ks_2samp(e, a)
        value = psi(e, a)
        out[col] = {
            "psi": round(value, 4),
            "ks_stat": round(float(ks.statistic), 4),
            "ks_p": round(float(ks.pvalue), 4),
            "nan_rate_live": round(float(live_features[col].isna().mean()), 4),
            "status": ("STABLE" if value < 0.10 else
                       "MINOR" if value < 0.25 else "SIGNIFICANT DRIFT"),
        }
    return out
```

Check `nan_rate_live` as carefully as the drift statistic. A feature that has quietly
become all-NaN produces a constant prediction and no drift alarm.

## 6. Realised versus expected

```python
import numpy as np
import pandas as pd


def realised_vs_expected(live_returns: pd.Series, backtest_returns: pd.Series,
                         live_slippage_bps=None, modelled_slippage_bps=None) -> dict:
    n = len(live_returns)
    exp_mu, exp_sd = backtest_returns.mean(), backtest_returns.std(ddof=1)
    obs_mu, obs_sd = live_returns.mean(), live_returns.std(ddof=1)
    se = exp_sd / np.sqrt(max(n, 1))
    z = (obs_mu - exp_mu) / se if se else 0.0

    out = {
        "live_periods": n,
        "expected_ann_return": round(float(exp_mu * 252), 4),
        "realised_ann_return": round(float(obs_mu * 252), 4),
        "expected_ann_vol": round(float(exp_sd * np.sqrt(252)), 4),
        "realised_ann_vol": round(float(obs_sd * np.sqrt(252)), 4),
        "z_vs_expected": round(float(z), 2),
        "verdict": ("within expectation" if abs(z) < 2 else
                    "materially below expectation" if z < 0 else
                    "materially above expectation"),
    }
    if live_slippage_bps is not None and modelled_slippage_bps:
        out["slippage_ratio"] = round(float(live_slippage_bps / modelled_slippage_bps), 2)
    return out
```

A `slippage_ratio` above 1.5 usually explains a return shortfall on its own, and it is
fixable through execution rather than through the model.

## 7. Safe rollout

```python
class ShadowRollout:
    """Run a candidate alongside the incumbent before giving it any capital."""

    def __init__(self, incumbent, candidate, allocation=0.0):
        self.incumbent, self.candidate = incumbent, candidate
        self.allocation = allocation
        self.log = []

    def predict(self, features):
        a, b = self.incumbent.predict(features), self.candidate.predict(features)
        self.log.append({"incumbent": a, "candidate": b})
        return (1 - self.allocation) * a + self.allocation * b

    def agreement(self):
        import numpy as np
        inc = np.array([r["incumbent"] for r in self.log]).ravel()
        can = np.array([r["candidate"] for r in self.log]).ravel()
        return {
            "n": len(inc),
            "correlation": float(np.corrcoef(inc, can)[0, 1]) if len(inc) > 2 else None,
            "sign_agreement": float((np.sign(inc) == np.sign(can)).mean()),
            "mean_abs_diff": float(np.abs(inc - can).mean()),
        }

    def promote(self, step=0.25):
        self.allocation = min(1.0, self.allocation + step)
        return self.allocation

    def rollback(self):
        self.allocation = 0.0
        return self.allocation
```

Ramp in steps with a stated observation period between them, and make `rollback` a
single command that anyone on the team can run.

## 8. Deployment checklist

- [ ] Holdout results recorded and unchanged since selection
- [ ] Parity check passed against research positions
- [ ] Replay against a live-shaped feed passed
- [ ] Order state machine covers every broker response, including unknown
- [ ] Idempotency keys on every order
- [ ] Reconciliation runs each cycle and halts on a break
- [ ] All circuit breakers configured, with limits written down and agreed
- [ ] Kill switch tested, from a second machine
- [ ] Alerting reaches a human out of hours
- [ ] Logging captures inputs, model version, predictions, intents, fills, breaker state
- [ ] Paper period duration and pass criteria agreed **before** it starts
- [ ] Initial live size set at a level where being wrong is affordable
- [ ] Scaling schedule and the metric that gates it written down
- [ ] Retraining policy decided in advance
- [ ] Runbook exists for: feed down, broker down, reconciliation break, breaker tripped
- [ ] Someone other than the author can stop the system
