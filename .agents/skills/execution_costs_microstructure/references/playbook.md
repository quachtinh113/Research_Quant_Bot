# Execution & Cost Playbook

## 1. Spread estimation from OHLC

```python
import numpy as np
import pandas as pd


def corwin_schultz_spread(high: pd.Series, low: pd.Series) -> pd.Series:
    """Two-day high-low spread estimator. Returns a proportional spread."""
    hl = np.log(high / low) ** 2
    beta = hl.rolling(2).sum()
    h2 = high.rolling(2).max()
    l2 = low.rolling(2).min()
    gamma = np.log(h2 / l2) ** 2

    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    alpha = alpha.clip(lower=0)
    return (2 * (np.exp(alpha) - 1)) / (1 + np.exp(alpha))


def roll_spread(close: pd.Series, window: int = 21) -> pd.Series:
    """Roll's serial-covariance estimator; valid only when the covariance is negative."""
    d = close.diff()
    cov = d.rolling(window).cov(d.shift(1))
    return 2 * np.sqrt((-cov).clip(lower=0)) / close
```

Sanity-check the output against published venue statistics. If a liquid large-cap
prints more than 20 basis points, the estimator is being fed bad bars.

## 2. Impact models

```python
import numpy as np


def square_root_impact(quantity, adv, daily_vol_bps, y=0.6):
    """Almgren square-root law. Returns one-way impact in basis points."""
    participation = np.clip(quantity / max(adv, 1.0), 0.0, 1.0)
    return float(y * daily_vol_bps * np.sqrt(participation))


def linear_temporary_impact(quantity, adv, eta_bps=10.0):
    return float(eta_bps * quantity / max(adv, 1.0))


def total_cost_bps(quantity, adv, daily_vol_bps, spread_bps,
                   commission_bps=0.5, y=0.6):
    return {
        "commission": commission_bps,
        "spread": spread_bps / 2.0,                       # marketable order
        "impact": square_root_impact(quantity, adv, daily_vol_bps, y),
        "total": commission_bps + spread_bps / 2.0
                 + square_root_impact(quantity, adv, daily_vol_bps, y),
    }
```

`y` between 0.4 and 1.0 covers most published equity estimates. Calibrate it against
your own fills if you have them; otherwise use 0.6 and say that you assumed it.

## 3. Capacity

```python
def capacity(alpha_bps_per_trade, adv, daily_vol_bps, spread_bps,
             turnover_per_year, y=0.6, participation_cap=0.05):
    """Largest notional at which expected alpha still exceeds expected cost."""
    lo, hi = 0.0, adv * participation_cap
    for _ in range(60):
        mid = (lo + hi) / 2
        cost = total_cost_bps(mid, adv, daily_vol_bps, spread_bps, y=y)["total"]
        if cost < alpha_bps_per_trade:
            lo = mid
        else:
            hi = mid
    per_trade = lo
    return {
        "max_trade_notional": per_trade,
        "implied_aum": per_trade / max(turnover_per_year / 252, 1e-9),
        "participation_at_max": per_trade / adv,
    }
```

`implied_aum` is the number to quote when someone asks how much the strategy can hold.
It is usually far smaller than expected, and that is useful information early.

## 4. Almgren-Chriss trajectory

```python
import numpy as np


def almgren_chriss(total_shares, n_periods, sigma, eta, gamma_perm,
                   risk_aversion=1e-6):
    """Optimal execution trajectory. eta = temporary impact, gamma_perm = permanent."""
    tau = 1.0 / n_periods
    kappa_sq = risk_aversion * sigma ** 2 / (eta * (1 - gamma_perm * tau / (2 * eta)))
    kappa = np.arccosh(kappa_sq * tau ** 2 / 2 + 1) / tau if kappa_sq > 0 else 0.0

    t = np.arange(n_periods + 1) * tau
    T = n_periods * tau
    if kappa > 0:
        holdings = total_shares * np.sinh(kappa * (T - t)) / np.sinh(kappa * T)
    else:
        holdings = total_shares * (1 - t / T)          # TWAP limit
    return {"holdings": holdings, "trades": -np.diff(holdings), "kappa": float(kappa)}
```

`risk_aversion` at zero gives TWAP. Raising it front-loads the schedule. When the
signal decays quickly, front-loading is correct even though it costs more impact.

## 5. Schedules

```python
import numpy as np
import pandas as pd


def twap_schedule(total, n_slices):
    return np.full(n_slices, total / n_slices)


def vwap_schedule(total, volume_profile):
    p = np.asarray(volume_profile, dtype=float)
    return total * p / p.sum()


def pov_schedule(total, volume_forecast, participation=0.10):
    """Percentage of volume, capped so the order finishes."""
    per_slice = np.asarray(volume_forecast, dtype=float) * participation
    filled = np.cumsum(per_slice)
    per_slice[filled > total] = 0.0
    remaining = total - per_slice.sum()
    if remaining > 0:
        per_slice[-1] += remaining
    return per_slice


def intraday_volume_profile(minute_volumes: pd.DataFrame) -> pd.Series:
    """Average U-shaped profile by minute of day, normalised to sum to one."""
    prof = minute_volumes.groupby(minute_volumes.index.time).mean().mean(axis=1)
    return prof / prof.sum()
```

The volume profile is U-shaped in most equity markets: heavy at the open and the close,
thin at midday. A TWAP that ignores it participates far above target in quiet hours.

## 6. Cost sensitivity, the deciding chart

```python
import pandas as pd


def cost_cascade(run_backtest, bps_grid=(0, 2, 5, 10, 15, 20, 30, 50, 75, 100)):
    rows = []
    for bps in bps_grid:
        res = run_backtest(cost_bps=bps)
        rows.append({"cost_bps": bps,
                     "sharpe": round(float(res["sharpe"]), 3),
                     "ann_return": round(float(res["ann_return"]), 4)})
    df = pd.DataFrame(rows)

    zero = None
    for a, b in zip(df.itertuples(), df.iloc[1:].itertuples()):
        if a.sharpe > 0 >= b.sharpe:
            zero = a.cost_bps + (b.cost_bps - a.cost_bps) * a.sharpe / (a.sharpe - b.sharpe)
            break
    df.attrs["zero_crossing_bps"] = zero
    df.attrs["verdict"] = (
        "robust" if zero and zero > 50 else
        "institutional only" if zero and zero > 15 else
        "not deployable"
    )
    return df
```

## 7. Microstructure features

```python
import numpy as np
import pandas as pd


def order_flow_imbalance(bid_size, ask_size, bid_price, ask_price):
    """Cont, Kukanov and Stoikov order flow imbalance from level-1 updates."""
    bp, ap = np.asarray(bid_price), np.asarray(ask_price)
    bs, as_ = np.asarray(bid_size), np.asarray(ask_size)
    e = np.zeros(len(bp))
    for i in range(1, len(bp)):
        db = bs[i] if bp[i] > bp[i - 1] else (bs[i] - bs[i - 1] if bp[i] == bp[i - 1] else -bs[i - 1])
        da = as_[i] if ap[i] < ap[i - 1] else (as_[i] - as_[i - 1] if ap[i] == ap[i - 1] else -as_[i - 1])
        e[i] = db - da
    return pd.Series(e)


def kyles_lambda(price_changes, signed_volume, window=100):
    """Price impact per unit of signed flow: the slope of dP on signed volume."""
    p = pd.Series(price_changes)
    v = pd.Series(signed_volume)
    cov = p.rolling(window).cov(v)
    var = v.rolling(window).var()
    return cov / var.replace(0, np.nan)


def vpin(buy_volume, sell_volume, n_buckets=50):
    b, s = pd.Series(buy_volume), pd.Series(sell_volume)
    return (b - s).abs().rolling(n_buckets).sum() / (b + s).rolling(n_buckets).sum()


def effective_spread(trade_price, mid_price, side):
    """side: +1 buy, -1 sell. Returned in basis points."""
    return 2 * side * (trade_price - mid_price) / mid_price * 10_000


def realised_spread(trade_price, mid_future, side):
    """The market maker's revenue: effective spread minus the informed component."""
    return 2 * side * (trade_price - mid_future) / mid_future * 10_000
```

`effective_spread` minus `realised_spread` is the price impact, which is the part
attributable to information in your order. If it is large, you are being adversely
selected and should trade more passively or in smaller pieces.

## 8. Engine-specific cost configuration

```python
# vectorbt: global defaults, then per-run overrides
import vectorbt as vbt
vbt.settings['portfolio']['fees'] = 0.0005
vbt.settings['portfolio']['slippage'] = 0.0005
vbt.settings['portfolio']['freq'] = '1d'

# size-dependent slippage: pass an array shaped like close
slippage = (participation ** 0.5 * daily_vol).clip(0.0002, 0.005)
pf = vbt.Portfolio.from_signals(close, entries, exits, slippage=slippage, freq='1d')
```

```python
# LEAN
def initialize(self):
    self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,
                             AccountType.MARGIN)
    self.set_security_initializer(self._init_security)

def _init_security(self, security):
    security.set_fee_model(InteractiveBrokersFeeModel())
    security.set_slippage_model(VolumeShareSlippageModel(volume_limit=0.025,
                                                        price_impact=0.10))
    security.set_fill_model(EquityFillModel())
```

```yaml
# Qlib
backtest:
  exchange_kwargs:
    limit_threshold: 0.095
    deal_price: close
    open_cost: 0.0005
    close_cost: 0.0015
    min_cost: 5
    impact_cost: 0.0
```

## 9. Borrow and funding

```python
def short_borrow_cost(notional, annual_rate, days, basis=360):
    return notional * annual_rate * days / basis


def perp_funding_cost(notional, funding_rate_8h, hours_held):
    """Perpetual funding accrues every eight hours and is often the whole return."""
    return notional * funding_rate_8h * (hours_held / 8.0)
```

For crypto carry, compute the funding series first and check whether the strategy is
anything other than a funding harvest with extra steps.

## 10. Reporting costs

Always report these five numbers together:

```text
Gross Sharpe                 : 1.62
Net Sharpe at assumed cost   : 0.94    (10 bps round trip)
Annual turnover              : 480%
Annual cost drag             : 4.8%
Sharpe zero-crossing         : 21 bps
```

The gap between gross and net is the honest measure of how much the strategy depends
on execution quality. A gap of more than half the gross Sharpe means execution is the
project, not the signal.
