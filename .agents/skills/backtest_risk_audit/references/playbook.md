# Audit Playbook

Concrete procedures with code. Everything here is stdlib, NumPy, SciPy and pandas.

## 1. Find lookahead mechanically

Before reading logic, grep for the patterns that cause it.

```bash
# negative shifts and forward references outside label code
grep -rnE "shift\(-[0-9]+\)|Ref\(\\\$?[a-z_]+, *-[0-9]+\)" --include=*.py .

# statistics fitted before a split
grep -rnE "\.fit\(.*(X|df|data)\)" --include=*.py . | head
grep -rnE "(StandardScaler|MinMaxScaler|RobustScaler)\(\)\.fit_transform" --include=*.py .

# whole-series rolling stats used across a split boundary
grep -rnE "rolling\([0-9]+\)\.(mean|std|max|min)\(\)" --include=*.py . | head -40

# resampling and interpolation that can pull future values backwards
grep -rnE "\.interpolate\(|\.bfill\(|fillna\(method=['\"]bfill" --include=*.py .
```

`bfill` is the quiet one. Backward-filling a price or a fundamental copies a future
value into the past, and it looks innocuous in a data-cleaning function.

## 2. The shift test

The most reliable detector of timing bugs needs no theory.

```python
def shift_test(run_backtest, data, extra_lag: int = 1):
    """A strategy whose result collapses under one extra bar of lag was using
    information it did not have."""
    base = run_backtest(data)
    lagged = run_backtest(data, extra_signal_lag=extra_lag)
    drop = (base["sharpe"] - lagged["sharpe"]) / max(abs(base["sharpe"]), 1e-9)
    return {
        "base_sharpe": base["sharpe"],
        "lagged_sharpe": lagged["sharpe"],
        "relative_drop": drop,
        "verdict": "LOOKAHEAD SUSPECTED" if drop > 0.5 else "acceptable sensitivity",
    }
```

Real edges decay with lag; they do not vanish. A drop of more than half from a single
extra bar means the signal was reading the bar it trades on.

## 3. Deflated Sharpe Ratio, end to end

```python
import numpy as np
from scipy import stats


def audit_significance(returns, n_trials, periods_per_year=252):
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = r.size
    if n < 30:
        return {"error": f"only {n} observations; no metric is informative"}

    sharpe_period = r.mean() / (r.std(ddof=1) + 1e-12)
    sharpe_annual = sharpe_period * np.sqrt(periods_per_year)
    skew = float(stats.skew(r))
    kurt = float(stats.kurtosis(r, fisher=False))

    e = np.euler_gamma
    sr0 = ((1 - e) * stats.norm.ppf(1 - 1.0 / n_trials)
           + e * stats.norm.ppf(1 - 1.0 / (n_trials * np.e))) if n_trials > 1 else 0.0

    denom = np.sqrt(max(1 - skew * sharpe_period
                        + (kurt - 1) / 4 * sharpe_period ** 2, 1e-12))
    dsr = float(stats.norm.cdf((sharpe_period - sr0) * np.sqrt(n - 1) / denom))

    # Minimum track record length for significance at 95%
    mintrl = 1 + denom ** 2 * (stats.norm.ppf(0.95) / (sharpe_period - sr0)) ** 2 \
        if sharpe_period > sr0 else float("inf")

    return {
        "observations": n,
        "annual_sharpe": round(sharpe_annual, 3),
        "skew": round(skew, 3),
        "kurtosis": round(kurt, 3),
        "trials": n_trials,
        "expected_max_sharpe_period": round(sr0, 4),
        "deflated_sharpe": round(dsr, 4),
        "min_track_record_periods": (round(mintrl) if np.isfinite(mintrl) else None),
        "significant_at_95": dsr > 0.95,
    }
```

`min_track_record_periods` is the underused output. It answers "how long would I need
to run this before the result could be significant", and the answer is frequently
longer than the strategy's expected shelf life.

## 4. Probability of backtest overfitting

```python
import itertools
import numpy as np


def pbo(perf_matrix, n_blocks=16):
    """perf_matrix: (T, C) array of per-period returns for C configurations."""
    perf_matrix = np.asarray(perf_matrix, dtype=float)
    T, C = perf_matrix.shape
    block = T // n_blocks
    blocks = [perf_matrix[i * block:(i + 1) * block] for i in range(n_blocks)]

    logits = []
    for combo in itertools.combinations(range(n_blocks), n_blocks // 2):
        rest = [i for i in range(n_blocks) if i not in combo]
        is_ = np.vstack([blocks[i] for i in combo])
        oos = np.vstack([blocks[i] for i in rest])

        def sharpe(a):
            return a.mean(axis=0) / (a.std(axis=0, ddof=1) + 1e-12)

        best = int(np.argmax(sharpe(is_)))
        oos_ranks = np.argsort(np.argsort(sharpe(oos)))
        w = (oos_ranks[best] + 1) / (C + 1)
        logits.append(np.log(w / (1 - w)))

    logits = np.asarray(logits)
    return {
        "pbo": float((logits <= 0).mean()),
        "median_logit": float(np.median(logits)),
        "splits": len(logits),
    }
```

Interpretation: PBO near 0 means the in-sample winner usually wins out of sample and
the selection procedure works. PBO above 0.5 means it is worse than picking at random,
and no amount of further tuning will help.

## 5. Cost sensitivity curve

```python
import pandas as pd


def cost_curve(run, bps=(0, 2, 5, 10, 15, 20, 30, 50), periods_per_year=252):
    rows = []
    for b in bps:
        r = run(cost_bps=b)["returns"]
        s = r.mean() / (r.std(ddof=1) + 1e-12) * (periods_per_year ** 0.5)
        rows.append({"cost_bps": b, "sharpe": round(float(s), 3)})
    df = pd.DataFrame(rows)

    crossing = None
    for a, c in zip(df.itertuples(), df.iloc[1:].itertuples()):
        if a.sharpe > 0 >= c.sharpe:
            span = a.sharpe - c.sharpe
            crossing = a.cost_bps + (c.cost_bps - a.cost_bps) * (a.sharpe / span)
            break
    df.attrs["zero_crossing_bps"] = crossing
    return df
```

Report the zero-crossing figure next to the headline Sharpe, always. It is the single
number that best predicts whether a paper strategy survives contact with a broker.

## 6. Random benchmark

```python
import numpy as np


def random_benchmark(price, n_trades, holding_period, n_paths=1000,
                     cost_bps=10, seed=0):
    rng = np.random.default_rng(seed)
    rets = np.diff(np.log(price))
    n = rets.size
    out = np.empty(n_paths)
    for k in range(n_paths):
        pos = np.zeros(n)
        starts = rng.choice(n - holding_period, size=n_trades, replace=False)
        for s in starts:
            pos[s:s + holding_period] = 1.0
        turns = np.abs(np.diff(pos, prepend=0.0))
        strat = pos * rets - turns * cost_bps / 10_000
        out[k] = strat.mean() / (strat.std(ddof=1) + 1e-12) * np.sqrt(252)
    return out
```

Then `p = (null >= observed).mean()`. Matching the trade count and holding period is
what makes the comparison fair; a random benchmark that trades far less often is not a
null hypothesis, it is a different strategy.

## 7. Drop-the-best test

```python
import numpy as np


def drop_best(returns, k=5):
    r = np.asarray(returns, dtype=float)
    order = np.argsort(r)[::-1]
    trimmed = np.delete(r, order[:k])
    def sh(a):
        return a.mean() / (a.std(ddof=1) + 1e-12) * np.sqrt(252)
    return {
        "sharpe_full": round(float(sh(r)), 3),
        f"sharpe_minus_top_{k}": round(float(sh(trimmed)), 3),
        "top_k_share_of_total": round(float(r[order[:k]].sum() / r.sum()), 3),
    }
```

If five days out of a thousand carry more than half the return, the strategy's
distribution is the story, and its Sharpe is close to meaningless.

## 8. Regime split

```python
REGIMES = {
    "pre_gfc":   ("2003-01-01", "2007-06-30"),
    "gfc":       ("2007-07-01", "2009-06-30"),
    "qe_bull":   ("2009-07-01", "2019-12-31"),
    "covid":     ("2020-01-01", "2020-12-31"),
    "inflation": ("2022-01-01", "2022-12-31"),
    "recent":    ("2023-01-01", None),
}


def by_regime(returns: "pd.Series"):
    import pandas as pd
    rows = []
    for name, (start, end) in REGIMES.items():
        seg = returns.loc[start:end] if end else returns.loc[start:]
        if len(seg) < 40:
            continue
        rows.append({
            "regime": name, "periods": len(seg),
            "ann_return": round(float(seg.mean() * 252), 4),
            "sharpe": round(float(seg.mean() / (seg.std(ddof=1) + 1e-12) * 252 ** 0.5), 3),
            "max_dd": round(float(((1 + seg).cumprod() /
                                   (1 + seg).cumprod().cummax() - 1).min()), 4),
        })
    return pd.DataFrame(rows)
```

Adjust the windows to the asset class. For crypto, use the 2018 and 2022 drawdowns.
For FX, use the periods around policy regime changes.

## 9. Factor attribution

Before calling anything alpha, regress it on the obvious factors.

```python
import numpy as np
import statsmodels.api as sm


def attribute(strategy_returns, factor_returns):
    """factor_returns: DataFrame with columns such as MKT, SMB, HML, MOM."""
    X = sm.add_constant(factor_returns.loc[strategy_returns.index].dropna())
    y = strategy_returns.loc[X.index]
    fit = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    return {
        "alpha_annual": round(float(fit.params["const"] * 252), 4),
        "alpha_tstat": round(float(fit.tvalues["const"]), 2),
        "loadings": {k: round(float(v), 3)
                     for k, v in fit.params.drop("const").items()},
        "r_squared": round(float(fit.rsquared), 3),
    }
```

Use HAC standard errors: strategy returns are autocorrelated and plain OLS t-statistics
overstate significance. An alpha t-statistic below 2 after this adjustment, on a
strategy selected from many trials, is not evidence.

## 10. Writing it up

Lead with the verdict. Give at most three blocking findings with file and line
references and the measured effect of each. Put the numbers in a small table. End with
the single most useful next step.

Resist two failure modes. The first is the exhaustive list, where twenty observations
of equal weight bury the one that matters. The second is the hedge, where every
finding is softened until the reader cannot tell whether to deploy. If the result is
not evidence, say it is not evidence.
