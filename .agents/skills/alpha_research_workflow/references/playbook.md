# Alpha Research Playbook

Working code for each stage. Pandas and NumPy only unless noted.

## 1. Feasibility in one function

```python
import numpy as np
import pandas as pd


def feasibility(prices: pd.DataFrame, volumes: pd.DataFrame,
                target_turnover_annual: float, cost_bps: float,
                capital: float, participation_cap: float = 0.05) -> dict:
    """Can this universe pay for the intended trading before any model exists?"""
    dollar_vol = (prices * volumes).median()
    tradable = dollar_vol[dollar_vol > 0]

    cost_drag = target_turnover_annual * cost_bps / 10_000
    per_name = capital / max(len(tradable), 1)
    participation = per_name / tradable.median()

    return {
        "names": int(len(tradable)),
        "median_daily_dollar_volume": float(tradable.median()),
        "annual_cost_drag": round(float(cost_drag), 4),
        "required_gross_return": round(float(cost_drag), 4),
        "participation_at_target": round(float(participation), 4),
        "participation_ok": bool(participation <= participation_cap),
        "verdict": ("feasible" if participation <= participation_cap and cost_drag < 0.05
                    else "marginal" if cost_drag < 0.10 else "infeasible"),
    }
```

An annual cost drag above 5% needs an exceptional signal. Above 10%, stop.

## 2. Labels

```python
def forward_return(close: pd.DataFrame, horizon: int, lag: int = 1) -> pd.DataFrame:
    """Decide at t, enter at t+lag, exit at t+lag+horizon."""
    entry = close.shift(-lag)
    exit_ = close.shift(-(lag + horizon))
    return exit_ / entry - 1.0


def excess_forward_return(close, benchmark_close, horizon, lag=1):
    r = forward_return(close, horizon, lag)
    b = forward_return(benchmark_close.to_frame().reindex(close.index).ffill(),
                       horizon, lag).iloc[:, 0]
    return r.sub(b, axis=0)


def triple_barrier(close: pd.Series, events: pd.DatetimeIndex,
                   pt: float, sl: float, max_hold: int) -> pd.DataFrame:
    """Label by which barrier is touched first: +1 profit, -1 stop, 0 timeout."""
    out = []
    for t0 in events:
        window = close.loc[t0:].iloc[:max_hold + 1]
        if len(window) < 2:
            continue
        path = window / window.iloc[0] - 1.0
        hit_pt = path[path >= pt].index.min()
        hit_sl = path[path <= -sl].index.min()
        first = min([x for x in (hit_pt, hit_sl) if pd.notna(x)], default=window.index[-1])
        label = 1 if first == hit_pt else (-1 if first == hit_sl else 0)
        out.append({"t0": t0, "t1": first, "label": label,
                    "ret": float(path.loc[first])})
    return pd.DataFrame(out).set_index("t0")
```

`triple_barrier` returns `t1`, the actual exit time. Keep it: it is what a purge
routine needs to know which training rows overlap a validation window.

## 3. Effective sample size with overlapping labels

```python
def effective_n(n_obs: int, horizon: int) -> int:
    """Overlapping forward returns share information; naive counts inflate t-stats."""
    return max(int(n_obs / max(horizon, 1)), 1)


def corrected_tstat(mean, std, n_obs, horizon):
    import numpy as np
    return float(mean / (std + 1e-12) * np.sqrt(effective_n(n_obs, horizon)))
```

A 21-day label sampled daily over 2,520 observations has an effective sample of about
120, and the naive t-statistic is roughly 4.6 times too large.

## 4. Feature families with a timing contract

```python
from dataclasses import dataclass
from typing import Callable, Dict
import pandas as pd


@dataclass(frozen=True)
class Feature:
    name: str
    family: str
    warmup: int                 # observations before the value is valid
    lookback_only: bool         # True if it never touches data at or after t
    fn: Callable[[pd.DataFrame], pd.Series]


def build(features, data: pd.DataFrame) -> pd.DataFrame:
    cols, warmup = {}, 0
    for f in features:
        assert f.lookback_only, f"{f.name} is not declared lookback-only"
        cols[f.name] = f.fn(data)
        warmup = max(warmup, f.warmup)
    out = pd.DataFrame(cols)
    out.iloc[:warmup] = pd.NA           # nothing is valid before the longest warm-up
    out.attrs["warmup"] = warmup
    out.attrs["families"] = sorted({f.family for f in features})
    return out
```

Blanking the warm-up window rather than letting partially-formed values through is
what stops the first year of a backtest from being fitted noise.

## 5. Purged walk-forward splits

```python
import numpy as np
import pandas as pd


def purged_walk_forward(index: pd.DatetimeIndex, n_splits: int,
                        train_size: int, val_size: int,
                        purge: int, embargo: int = 0):
    """Yield (train_idx, val_idx) with a purge gap and a trailing embargo."""
    n = len(index)
    step = (n - train_size - val_size) // max(n_splits - 1, 1) if n_splits > 1 else 0
    for k in range(n_splits):
        tr_end = train_size + k * step
        va_start = tr_end + purge
        va_end = va_start + val_size
        if va_end > n:
            break
        train = np.arange(max(0, tr_end - train_size), tr_end)
        val = np.arange(va_start, va_end)
        if embargo:
            train = train[train < va_start - purge - embargo]
        yield train, val
```

`purge` must be at least the label horizon. `embargo` guards against features whose
serial correlation reaches backwards; a few days is usually enough for daily data.

## 6. Information coefficient, the full read

```python
import numpy as np
import pandas as pd
from scipy import stats


def ic_report(pred: pd.Series, label: pd.Series, n_buckets: int = 10) -> dict:
    """pred and label share a (datetime, instrument) MultiIndex."""
    df = pd.concat([pred.rename("p"), label.rename("y")], axis=1).dropna()
    by_date = df.groupby(level=0)

    ic = by_date.apply(lambda g: g["p"].corr(g["y"]))
    ric = by_date.apply(lambda g: g["p"].corr(g["y"], method="spearman"))

    buckets = by_date.apply(
        lambda g: g.assign(b=pd.qcut(g["p"].rank(method="first"), n_buckets,
                                     labels=False, duplicates="drop"))
                   .groupby("b")["y"].mean()
    )
    profile = buckets.mean() if isinstance(buckets, pd.DataFrame) else buckets.unstack().mean()
    monotone = bool(np.all(np.diff(profile.values) > -profile.std() * 0.25))

    return {
        "ic_mean": round(float(ic.mean()), 4),
        "ic_std": round(float(ic.std()), 4),
        "icir_annual": round(float(ic.mean() / (ic.std() + 1e-12) * np.sqrt(252)), 3),
        "rank_ic_mean": round(float(ric.mean()), 4),
        "rank_icir_annual": round(float(ric.mean() / (ric.std() + 1e-12) * np.sqrt(252)), 3),
        "positive_rate": round(float((ric > 0).mean()), 3),
        "tstat": round(float(stats.ttest_1samp(ric.dropna(), 0).statistic), 2),
        "bucket_profile": [round(float(v), 5) for v in profile.values],
        "monotone": monotone,
        "periods": int(len(ric)),
    }
```

Then check stability by fold before believing the pooled numbers:

```python
def ic_by_fold(pred, label, folds):
    return pd.DataFrame([
        {"fold": i, **ic_report(pred.iloc[v], label.iloc[v])}
        for i, (_, v) in enumerate(folds)
    ])[["fold", "rank_ic_mean", "rank_icir_annual", "positive_rate", "periods"]]
```

Report the number of folds with a positive rank IC. Five of eight is weak evidence;
eight of eight with modest magnitude is much stronger than one fold with a large one.

## 7. Signal decay

```python
def decay_profile(pred: pd.Series, close: pd.DataFrame,
                  horizons=(1, 2, 3, 5, 10, 21, 42)) -> pd.DataFrame:
    rows = []
    for h in horizons:
        y = forward_return(close, h).stack()
        joined = pd.concat([pred.rename("p"), y.rename("y")], axis=1).dropna()
        ric = joined.groupby(level=0).apply(
            lambda g: g["p"].corr(g["y"], method="spearman"))
        rows.append({"horizon": h,
                     "rank_ic": round(float(ric.mean()), 4),
                     "icir": round(float(ric.mean() / (ric.std() + 1e-12)), 3)})
    df = pd.DataFrame(rows)
    df.attrs["peak_horizon"] = int(df.loc[df["rank_ic"].idxmax(), "horizon"])
    return df
```

The peak horizon is your holding period. If it is 1 and the profile is zero by 3, price
the strategy at institutional execution costs before going further.

## 8. Multiple-testing control

```python
import numpy as np


def benjamini_hochberg(pvalues, alpha=0.05):
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    ranked = p[order]
    m = len(p)
    thresh = alpha * (np.arange(1, m + 1) / m)
    passing = ranked <= thresh
    cutoff = np.max(np.where(passing)[0]) + 1 if passing.any() else 0
    keep = np.zeros(m, dtype=bool)
    keep[order[:cutoff]] = True
    return keep, (ranked[cutoff - 1] if cutoff else 0.0)


class TrialLog:
    """The count that every significance statement depends on."""

    def __init__(self):
        self.rows = []

    def record(self, description, metric, value, split):
        self.rows.append({"n": len(self.rows) + 1, "description": description,
                          "metric": metric, "value": value, "split": split})
        return len(self.rows)

    @property
    def count(self):
        return len(self.rows)
```

Instantiate one `TrialLog` per research question and pass it everywhere. If a
configuration was scored, it was a trial.

## 9. Feature triage

When a signal is weak, cut rather than add.

```python
def triage(features: pd.DataFrame, label: pd.Series, max_corr=0.9) -> dict:
    ic = features.apply(lambda c: c.corr(label, method="spearman"))
    corr = features.corr(method="spearman").abs()

    drop, kept = set(), []
    for name in ic.abs().sort_values(ascending=False).index:
        if name in drop:
            continue
        kept.append(name)
        redundant = corr.index[(corr[name] > max_corr) & (corr.index != name)]
        drop.update(redundant)

    return {"kept": kept, "dropped_redundant": sorted(drop),
            "ic": ic.round(4).to_dict()}
```

Ten momentum windows are one feature with ten labels. Keeping all ten does not improve
the signal, but it does multiply the trial count.

## 10. What to record for the handover

```python
handover = {
    "hypothesis": "...",
    "universe": {"name": "...", "n_names": 0, "median_dollar_volume": 0.0},
    "label": {"type": "forward_return", "horizon": 21, "lag": 1,
              "cross_sectional": True},
    "features": {"families": [...], "count": 0, "warmup": 0},
    "splits": {"scheme": "walk_forward", "n_splits": 8, "train": 756,
               "val": 252, "purge": 21, "embargo": 5},
    "model": {"family": "lgbm", "preset": "config/lgb/default.yaml"},
    "validation": {"rank_ic": 0.0, "rank_icir": 0.0, "folds_positive": "0/8"},
    "decay": {"peak_horizon": 21},
    "trials": 0,
    "holdout_touched": False,
}
```

Anything the next stage has to guess at will be guessed wrong.
