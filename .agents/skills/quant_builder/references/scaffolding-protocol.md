# Scaffolding Protocol

The concrete steps for turning a request into a working pipeline.

## Step 0 — Restate the request as a specification

Before writing code, write four lines and confirm they match what was asked:

```text
UNIVERSE : liquid US ETFs, membership as of each date, 2010-2024
SIGNAL   : 12-month momentum minus 1-month reversal, cross-sectional rank
HORIZON  : 21 trading days, monthly rebalance
CONSTRAINT: long only, max 10% per name, 5 bps fees, 5 bps slippage
```

Ambiguity here becomes rework later. If the request does not settle one of these, pick
the conventional default, state it, and continue rather than blocking.

## Step 1 — Data contract

```python
# data/loaders.py
from dataclasses import dataclass
from typing import Sequence
import pandas as pd


@dataclass(frozen=True)
class DataContract:
    source: str
    point_in_time: bool
    includes_delisted: bool
    adjustment: str            # "raw+factors" | "back_adjusted" | "none"
    calendar: str
    start: str
    end: str


CONTRACT = DataContract(
    source="ml4t.data.load_etfs",
    point_in_time=True,
    includes_delisted=True,
    adjustment="raw+factors",
    calendar="XNYS",
    start="2010-01-01",
    end="2024-12-31",
)


def load(symbols: Sequence[str]) -> pd.DataFrame:
    from data import load_etfs
    df = load_etfs()
    report = validate_ohlcv(df)
    if not report["ok"]:
        raise ValueError(f"data quality gate failed: {report['issues']}")
    return df
```

Declaring the contract as a frozen dataclass means the assumptions are inspectable
rather than implied. `back_adjusted` with `point_in_time=True` is a contradiction, and
writing it down is how you notice.

## Step 2 — Labels

```python
# labels/definitions.py
LABEL = {
    "name": "fwd_21d_excess",
    "horizon": 21,
    "lag": 1,                     # decide at t, enter at t+1
    "definition": "close[t+22]/close[t+1] - 1, minus the equal-weight universe return",
    "cross_sectional": True,
    "overlap": "daily sampling of a 21-day return; purge 21 days in CV",
}


def build_label(close, lag=1, horizon=21):
    fwd = close.shift(-(lag + horizon)) / close.shift(-lag) - 1
    return fwd.sub(fwd.mean(axis=1), axis=0)
```

Keep the dictionary next to the function. It is what a reviewer reads first and what
the split geometry is derived from.

## Step 3 — Features

```python
# features/families.py
from dataclasses import dataclass
from typing import Callable
import pandas as pd


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    family: str
    warmup: int
    fn: Callable[[pd.DataFrame], pd.DataFrame]
    note: str = ""


SPECS = [
    FeatureSpec("mom_252_21", "momentum", 252,
                lambda p: p.shift(21) / p.shift(252) - 1,
                "12-1 momentum, skipping the last month"),
    FeatureSpec("rev_21", "reversal", 21,
                lambda p: -(p / p.shift(21) - 1)),
    FeatureSpec("vol_63", "volatility", 63,
                lambda p: p.pct_change().rolling(63).std()),
    FeatureSpec("dd_252", "drawdown", 252,
                lambda p: p / p.rolling(252).max() - 1),
]


def build(prices: pd.DataFrame) -> dict:
    warmup = max(s.warmup for s in SPECS)
    out = {s.name: s.fn(prices) for s in SPECS}
    for name in out:
        out[name].iloc[:warmup] = pd.NA
    return {"features": out, "warmup": warmup,
            "families": sorted({s.family for s in SPECS})}
```

Every feature above uses only backward shifts. That is checkable by reading, which is
the point.

## Step 4 — Splits from configuration

```yaml
# config/setup.yaml
universe:
  source: etfs
  min_dollar_volume: 5_000_000
cadence:
  rebalance: monthly
labels:
  horizon: 21
  lag: 1
walk_forward:
  n_splits: 8
  train_size: 756
  val_size: 252
  purge: 21          # equals the label horizon
  embargo: 5
costs:
  fees_bps: 5
  slippage_bps: 5
  participation_cap: 0.05
holdout:
  start: "2022-01-01"
  touched: false
```

`purge` equal to `labels.horizon` is not a coincidence and should not be tuned. The
`holdout.touched` flag is a discipline device: flip it in the config when the holdout
is used, and it becomes visible in every diff afterwards.

## Step 5 — Baseline first

```python
# models/baseline.py
from sklearn.linear_model import Ridge


def fit_baseline(X_train, y_train, alpha=1.0, seed=0):
    return Ridge(alpha=alpha, random_state=seed).fit(X_train, y_train)
```

Report its validation information coefficient before writing the candidate. If the
candidate cannot beat it across folds, the candidate is not an improvement.

## Step 6 — Candidate, with the import order that matters

```python
# models/candidate.py
import lightgbm as lgb          # before sklearn: OpenMP runtime binding
from sklearn.metrics import mean_squared_error


def fit_candidate(X_train, y_train, X_val, y_val, params: dict, seed=0):
    model = lgb.LGBMRegressor(random_state=seed, **params)
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(50, verbose=False)])
    return model
```

`params` comes from `config/model.yaml`. Never inline a grid.

## Step 7 — Evaluate the signal, not the equity curve

```python
# simulation/evaluate.py
def evaluate(predictions, labels, folds):
    rows = []
    for i, (_, val_idx) in enumerate(folds):
        rows.append({"fold": i, **ic_report(predictions.iloc[val_idx],
                                            labels.iloc[val_idx])})
    df = pd.DataFrame(rows)
    return {
        "by_fold": df,
        "folds_positive": int((df["rank_ic_mean"] > 0).sum()),
        "n_folds": len(df),
        "mean_rank_ic": float(df["rank_ic_mean"].mean()),
        "verdict": "proceed" if (df["rank_ic_mean"] > 0).sum() >= len(df) * 0.75
                   else "signal not stable across folds",
    }
```

Stop here if the verdict is negative. Building a portfolio on an unstable signal wastes
the rest of the pipeline and produces a number that will not replicate.

## Step 8 — Portfolio

```python
# portfolio/allocation.py
def target_weights(predictions, vol, config):
    w = decile_long_short(predictions, vol, gross=1.0) \
        if config["long_short"] else proportional(predictions, cap=config["max_weight"])
    w = cap_weights(w, config["max_weight"])
    w, info = vol_target(w, returns_history,
                         target_annual=config["target_vol"],
                         max_leverage=config["max_leverage"])
    return w, info
```

## Step 9 — Costs, and the curve

```python
# simulation/backtest.py
def run(config, cost_bps=None):
    cost = cost_bps if cost_bps is not None else (
        config["costs"]["fees_bps"] + config["costs"]["slippage_bps"])
    ...
    return {"returns": net, "sharpe": sharpe, "turnover": turnover,
            "cost_bps": cost}


CURVE = cost_cascade(run)     # always produced, always reported
```

## Step 10 — The entry point

```python
# run.py
import argparse, json, random
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/setup.yaml")
    ap.add_argument("--stage", choices=["features", "train", "evaluate",
                                        "backtest", "holdout"], required=True)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    cfg = load_config(args.config)
    if args.stage == "holdout" and cfg["holdout"]["touched"]:
        raise SystemExit("holdout already used; results would not be out-of-sample")
    ...
```

Guarding the holdout in code rather than in a comment is what makes the discipline
survive a deadline.

## Step 11 — The README the reviewer reads first

```markdown
# <Strategy name>

**Hypothesis**: <one paragraph, written before the first run>

**Universe**: <what, how many, as-of membership, liquidity filter>
**Label**: <definition, horizon, lag>
**Features**: <families, count, warm-up>
**Splits**: <scheme, folds, purge, embargo>
**Model**: <baseline result, candidate result, both on validation>
**Costs**: <assumption and its source>
**Trials**: <total configurations evaluated>
**Holdout**: <untouched | result>

## Run
    python run.py --stage features
    python run.py --stage train
    python run.py --stage evaluate
    python run.py --stage backtest

## Known limitations
- <the things you would attack first>
```

## Porting between engines

| From vectorbt | To LEAN | To Qlib |
|---|---|---|
| `entries.vbt.signals.fshift(1)` | scheduled event, or next-open fill | label already lags |
| `fees=0.0005` | `set_fee_model` | `open_cost` / `close_cost` |
| `slippage=0.0005` | `VolumeShareSlippageModel` | `impact_cost` |
| `size_type="targetpercent"` | `set_holdings(symbol, w)` | `WeightStrategyBase` |
| `group_by=True, cash_sharing=True` | inherent | inherent |
| grid over columns | `lean optimize` with `get_parameter` | sweep in the workflow YAML |

Expect the Sharpe to fall as you move right in fill realism. Report the gap; it is the
cost of the assumptions the faster engine let you make.
