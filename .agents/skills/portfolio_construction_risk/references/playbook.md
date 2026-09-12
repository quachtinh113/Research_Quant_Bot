# Portfolio Construction Playbook

NumPy, pandas and SciPy. No optimiser dependency required except where noted.

## 1. Covariance you can actually use

```python
import numpy as np


def ledoit_wolf(returns: np.ndarray) -> np.ndarray:
    """Shrink the sample covariance toward a scaled identity."""
    X = returns - returns.mean(axis=0)
    n, p = X.shape
    S = X.T @ X / n
    mu = np.trace(S) / p
    target = mu * np.eye(p)

    d2 = ((S - target) ** 2).sum()
    b2 = sum(((np.outer(X[i], X[i]) - S) ** 2).sum() for i in range(n)) / n ** 2
    shrink = float(np.clip(b2 / d2 if d2 > 0 else 0.0, 0.0, 1.0))
    return shrink * target + (1 - shrink) * S


def ewma_cov(returns: np.ndarray, halflife: int = 63) -> np.ndarray:
    lam = 0.5 ** (1 / halflife)
    w = lam ** np.arange(len(returns))[::-1]
    w /= w.sum()
    X = returns - np.average(returns, axis=0, weights=w)
    return (X * w[:, None]).T @ X / (1 - (w ** 2).sum())
```

Use shrinkage whenever the number of assets approaches the number of observations. The
unshrunk sample covariance is near-singular there and any optimiser inverting it will
produce nonsense with great confidence.

## 2. Allocators

```python
import numpy as np
from scipy.cluster.hierarchy import linkage, to_tree
from scipy.spatial.distance import squareform
from scipy.optimize import minimize


def equal_weight(n):
    return np.ones(n) / n


def inverse_vol(cov):
    iv = 1.0 / np.sqrt(np.diag(cov))
    return iv / iv.sum()


def risk_parity(cov, tol=1e-10):
    n = len(cov)
    def obj(w):
        port_var = w @ cov @ w
        rc = w * (cov @ w) / np.sqrt(port_var)
        return ((rc - rc.mean()) ** 2).sum()
    res = minimize(obj, equal_weight(n), method="SLSQP",
                   bounds=[(0.0, 1.0)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"ftol": tol, "maxiter": 500})
    return res.x


def mean_variance(mu, cov, risk_aversion=1.0, w_min=0.0, w_max=0.10):
    n = len(mu)
    def neg_utility(w):
        return -(w @ mu - 0.5 * risk_aversion * w @ cov @ w)
    res = minimize(neg_utility, equal_weight(n), method="SLSQP",
                   bounds=[(w_min, w_max)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}])
    return res.x


def hrp(cov):
    """Hierarchical risk parity: cluster, quasi-diagonalise, recursively bisect."""
    std = np.sqrt(np.diag(cov))
    corr = cov / np.outer(std, std)
    dist = np.sqrt(np.clip((1 - corr) / 2, 0, 1))
    link = linkage(squareform(dist, checks=False), method="single")

    def leaves(node):
        return [node.id] if node.is_leaf() else leaves(node.left) + leaves(node.right)

    order = leaves(to_tree(link))

    def cluster_var(idx):
        sub = cov[np.ix_(idx, idx)]
        w = inverse_vol(sub)
        return float(w @ sub @ w)

    w = np.ones(len(cov))
    clusters = [order]
    while clusters:
        clusters = [c[i:j] for c in clusters
                    for i, j in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        for a, b in zip(clusters[0::2], clusters[1::2]):
            va, vb = cluster_var(a), cluster_var(b)
            alpha = 1 - va / (va + vb)
            w[a] *= alpha
            w[b] *= 1 - alpha
    return w / w.sum()
```

HRP needs no matrix inversion, which is exactly why it degrades gracefully when the
covariance estimate is poor. That is most of the time.

## 3. Signal to weights

```python
import numpy as np
import pandas as pd


def decile_long_short(pred: pd.Series, vol: pd.Series,
                      n_buckets: int = 10, gross: float = 1.0) -> pd.Series:
    """Long the top bucket, short the bottom, inverse-vol within each."""
    ranks = pred.rank(method="first")
    bucket = pd.qcut(ranks, n_buckets, labels=False, duplicates="drop")
    longs, shorts = bucket == n_buckets - 1, bucket == 0

    w = pd.Series(0.0, index=pred.index)
    for mask, sign in ((longs, 1.0), (shorts, -1.0)):
        if mask.sum() == 0:
            continue
        iv = 1.0 / vol[mask].clip(lower=vol.median() * 0.2)
        w[mask] = sign * gross / 2 * iv / iv.sum()
    return w


def proportional(pred: pd.Series, cap: float = 0.05, gross: float = 1.0) -> pd.Series:
    z = (pred - pred.mean()) / (pred.std(ddof=1) + 1e-12)
    w = z.clip(-3, 3)
    w = w / w.abs().sum() * gross
    return cap_weights(w, cap)


def cap_weights(w: pd.Series, cap: float) -> pd.Series:
    """Cap absolute weights and redistribute the excess proportionally."""
    w = w.copy()
    for _ in range(50):
        over = w.abs() > cap
        if not over.any():
            break
        excess = (w[over].abs() - cap).sum()
        w[over] = np.sign(w[over]) * cap
        room = (~over) & (w.abs() > 0)
        if not room.any():
            break
        w[room] += np.sign(w[room]) * excess * w[room].abs() / w[room].abs().sum()
    return w
```

The `clip(lower=median * 0.2)` on volatility matters. Without a floor, one
near-zero-volatility name absorbs the entire book.

## 4. Volatility targeting

```python
def vol_target(weights, returns_history, target_annual=0.12,
               lookback=63, max_leverage=2.0, floor=0.02, periods=252):
    """Scale to a forecast volatility, not a trailing one, with a floor."""
    port = (returns_history * weights).sum(axis=1)
    ewma = port.ewm(halflife=lookback // 3).std().iloc[-1]
    simple = port.tail(lookback).std(ddof=1)
    forecast = max(0.5 * ewma + 0.5 * simple, floor / (periods ** 0.5))
    realised_annual = forecast * (periods ** 0.5)
    scale = min(target_annual / realised_annual, max_leverage)
    return weights * scale, {"forecast_vol": realised_annual, "scale": scale}
```

Blending the EWMA and the simple estimate reduces the whipsaw that a pure EWMA
produces after a single large day.

## 5. Turnover control

```python
import numpy as np
import pandas as pd


def no_trade_band(current: pd.Series, target: pd.Series,
                  band: float = 0.002) -> pd.Series:
    """Only move a weight when the drift exceeds the band."""
    delta = target - current.reindex(target.index).fillna(0.0)
    return current.reindex(target.index).fillna(0.0).where(delta.abs() < band, target)


def turnover_penalised(mu, cov, w_prev, cost_bps=10.0,
                       risk_aversion=1.0, w_max=0.10):
    from scipy.optimize import minimize
    n, c = len(mu), cost_bps / 10_000
    def obj(w):
        return -(w @ mu - 0.5 * risk_aversion * w @ cov @ w
                 - c * np.abs(w - w_prev).sum())
    res = minimize(obj, w_prev, method="SLSQP",
                   bounds=[(0.0, w_max)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}])
    return res.x


def annual_turnover(weights: pd.DataFrame, periods_per_year=252) -> float:
    changes = weights.diff().abs().sum(axis=1)
    return float(changes.mean() * periods_per_year)
```

A no-trade band is the cheapest turnover reduction available and usually costs almost
nothing in return. Try it before reaching for a penalised optimiser.

## 6. Risk metrics

```python
import numpy as np


def var_cvar(returns, alpha=0.95, method="historical"):
    r = np.sort(np.asarray(returns, dtype=float))
    if method == "historical":
        idx = int((1 - alpha) * len(r))
        var = -r[idx]
        cvar = -r[:idx].mean() if idx > 0 else var
    else:
        from scipy.stats import norm
        mu, sd = r.mean(), r.std(ddof=1)
        var = -(mu + sd * norm.ppf(1 - alpha))
        cvar = -(mu - sd * norm.pdf(norm.ppf(1 - alpha)) / (1 - alpha))
    return {"var": float(var), "cvar": float(cvar), "alpha": alpha}


def drawdown_stats(returns):
    import pandas as pd
    eq = (1 + pd.Series(returns)).cumprod()
    peak = eq.cummax()
    dd = eq / peak - 1
    trough = dd.idxmin()
    peak_at = eq.loc[:trough].idxmax()
    after = eq.loc[trough:]
    recovered = after[after >= eq.loc[peak_at]]
    return {
        "max_drawdown": float(dd.min()),
        "peak": peak_at, "trough": trough,
        "recovery": recovered.index[0] if len(recovered) else None,
        "time_under_water": int((dd < 0).sum()),
    }
```

Report `time_under_water` alongside the depth. A 20% drawdown lasting three years and
one lasting two months are different businesses.

## 7. Factor attribution

```python
import statsmodels.api as sm


def exposures(strategy_returns, factors):
    X = sm.add_constant(factors.reindex(strategy_returns.index).dropna())
    y = strategy_returns.reindex(X.index)
    fit = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    return {
        "alpha_annual": float(fit.params["const"] * 252),
        "alpha_t": float(fit.tvalues["const"]),
        "betas": fit.params.drop("const").round(3).to_dict(),
        "r2": float(fit.rsquared),
    }
```

An R-squared above 0.7 against standard factors means the strategy is mostly a factor
portfolio. That may be fine, but price it as beta, not as alpha.

## 8. Stress testing

```python
import numpy as np


def correlation_shock(cov, rho=0.9):
    """In a crisis, correlations converge. Re-price the book under that assumption."""
    std = np.sqrt(np.diag(cov))
    shocked_corr = np.full_like(cov, rho)
    np.fill_diagonal(shocked_corr, 1.0)
    return shocked_corr * np.outer(std, std)


def scenario_pnl(weights, shocks: dict) -> dict:
    """shocks: {name: array of per-asset returns}."""
    return {name: float(weights @ s) for name, s in shocks.items()}
```

Standard scenarios worth keeping: equities −20% with a correlation shock, rates +200
basis points, credit spreads +300, a currency devaluation of 15%, and a liquidity
event where the participation cap halves.

## 9. Kelly, fractional

```python
import numpy as np


def kelly_weights(mu, cov, fraction=0.25, max_leverage=1.0):
    w = np.linalg.pinv(cov) @ mu
    gross = np.abs(w).sum()
    if gross > 0:
        w = w / gross * min(gross, max_leverage)
    return w * fraction
```

`pinv` rather than `inv`, because the covariance will be near-singular often enough
that a hard inverse fails in production at the worst moment.

## 10. Compare allocators honestly

```python
import pandas as pd


def compare(returns: pd.DataFrame, allocators: dict,
            lookback=252, rebalance=21, cost_bps=10.0):
    results = {}
    for name, fn in allocators.items():
        weights, dates = [], []
        for i in range(lookback, len(returns), rebalance):
            window = returns.iloc[i - lookback:i]
            cov = ledoit_wolf(window.to_numpy())
            weights.append(fn(cov))
            dates.append(returns.index[i])
        W = pd.DataFrame(weights, index=dates, columns=returns.columns)
        W = W.reindex(returns.index).ffill().fillna(0.0)
        gross = (W * returns).sum(axis=1)
        cost = W.diff().abs().sum(axis=1) * cost_bps / 10_000
        net = gross - cost
        results[name] = {
            "sharpe_gross": float(gross.mean() / gross.std(ddof=1) * 252 ** 0.5),
            "sharpe_net": float(net.mean() / net.std(ddof=1) * 252 ** 0.5),
            "turnover": float(W.diff().abs().sum(axis=1).mean() * 252),
            "max_dd": float(((1 + net).cumprod() /
                             (1 + net).cumprod().cummax() - 1).min()),
        }
    return pd.DataFrame(results).T
```

Always include equal weight in the comparison. If the sophisticated allocator does not
beat it net of cost, use equal weight and spend the time elsewhere.
