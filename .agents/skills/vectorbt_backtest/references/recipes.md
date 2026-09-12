# VectorBT Recipes

Every recipe assumes the project preamble below.

```python
import numpy as np
import pandas as pd
import vectorbt as vbt

vbt.settings['portfolio']['fees'] = 0.0005        # 5 bps
vbt.settings['portfolio']['slippage'] = 0.0005    # 5 bps
vbt.settings['portfolio']['freq'] = '1d'
vbt.settings['returns']['year_freq'] = '252 days'
```

## Recipe 1 — Honest crossover baseline

```python
close = vbt.YFData.download(["SPY"], start="2010-01-01", end="2024-12-31").get("Close")

fast = vbt.MA.run(close, 20, short_name="fast").ma
slow = vbt.MA.run(close, 100, short_name="slow").ma

entries = fast.vbt.crossed_above(slow).vbt.signals.fshift(1)
exits = fast.vbt.crossed_below(slow).vbt.signals.fshift(1)

pf = vbt.Portfolio.from_signals(
    close, entries, exits,
    size=1.0, size_type="percent", direction="longonly",
    init_cash=100_000, freq="1d",
)
stats = pf.stats()
print(stats)

gross_profit = pf.final_value() - pf.init_cash
print(f"fees paid {stats['Total Fees Paid']:,.0f} against gross profit {gross_profit:,.0f}")
```

The `fshift(1)` is the whole difference between a plausible result and a fantasy.

## Recipe 2 — Parameter grid with the trial count recorded

```python
FAST = [5, 10, 20, 30, 50]
SLOW = [50, 100, 150, 200]

fast = vbt.MA.run(close, window=FAST, short_name="fast")
slow = vbt.MA.run(close, window=SLOW, short_name="slow")

entries = fast.ma_crossed_above(slow).vbt.signals.fshift(1)
exits = fast.ma_crossed_below(slow).vbt.signals.fshift(1)

pf = vbt.Portfolio.from_signals(close, entries, exits,
                                size=1.0, size_type="percent", freq="1d")

n_trials = entries.shape[1]                        # carry this number forward
sharpe = pf.sharpe_ratio().sort_values(ascending=False)
print(f"{n_trials} configurations tested")
print(sharpe.head(10))
print(f"median Sharpe across the grid: {sharpe.median():.3f}")
```

Report the median alongside the maximum. A grid whose median Sharpe is near zero and
whose maximum is 1.8 has found noise, not an edge.

## Recipe 3 — Deflate the best result in place

```python
best_col = pf.sharpe_ratio().idxmax()
best_returns = pf.returns()[best_col]

dsr = best_returns.vbt.returns.deflated_sharpe_ratio(trials=n_trials)
print(f"observed Sharpe {best_returns.vbt.returns.sharpe_ratio():.3f}")
print(f"deflated Sharpe {dsr:.3f}")
```

A deflated Sharpe below roughly 0.5 after accounting for the trial count means the
grid has not produced evidence, whatever the raw number said.

## Recipe 4 — Walk-forward selection

```python
(in_price, in_idx), (out_price, out_idx) = close.vbt.rolling_split(
    n=8, window_len=252 * 4, set_lens=(252,), left_to_right=False,
)

def run(price):
    f = vbt.MA.run(price, window=FAST, short_name="fast")
    s = vbt.MA.run(price, window=SLOW, short_name="slow")
    e = f.ma_crossed_above(s).vbt.signals.fshift(1)
    x = f.ma_crossed_below(s).vbt.signals.fshift(1)
    return vbt.Portfolio.from_signals(price, e, x, size=1.0,
                                      size_type="percent", freq="1d")

in_pf, out_pf = run(in_price), run(out_price)

best_params = in_pf.sharpe_ratio().groupby("split_idx").idxmax()
oos = pd.Series({split: out_pf.sharpe_ratio()[col] for split, col in best_params.items()})
print(oos.describe())
```

The number that matters is the mean of `oos`, not the in-sample maximum. If the
out-of-sample mean is negative while the in-sample maximum is high, the parameter
surface is unstable and the strategy is not deployable.

## Recipe 5 — A real multi-asset portfolio

Independent columns are not a portfolio. Group them and share the cash.

```python
symbols = ["SPY", "QQQ", "IWM", "EFA", "TLT", "GLD"]
prices = vbt.YFData.download(symbols, start="2012-01-01").get("Close")

mom = prices.pct_change(126)
rank = mom.rank(axis=1, ascending=False)
target = (rank <= 3).astype(float)
target = target.div(target.sum(axis=1), axis=0).fillna(0.0)
target = target.shift(1).fillna(0.0)                   # trade on the next bar

month_end = ~target.index.to_period("M").duplicated(keep="last")
target = target.where(pd.Series(month_end, index=target.index), np.nan).ffill()

pf = vbt.Portfolio.from_orders(
    close=prices,
    size=target,
    size_type="targetpercent",
    group_by=True,                 # one portfolio, not six backtests
    cash_sharing=True,
    call_seq="auto",               # sells execute before buys
    init_cash=1_000_000,
    freq="1d",
)
print(pf.stats())
```

`call_seq="auto"` matters: without it, buys can be rejected because the sells that
would have funded them have not executed yet in the same bar.

## Recipe 6 — Stops that behave like real stops

```python
pf = vbt.Portfolio.from_signals(
    close, entries, exits,
    open=ohlcv["Open"], high=ohlcv["High"], low=ohlcv["Low"],
    sl_stop=0.05,
    sl_trail=True,
    tp_stop=0.15,
    stop_entry_price="close",
    stop_exit_price="stoplimit",
    freq="1d",
)
```

Passing `open`, `high` and `low` lets vectorbt detect an intrabar stop hit. Without
them, the stop can only trigger on the close, which understates how often you are
taken out and overstates the strategy.

## Recipe 7 — A custom indicator through the factory

```python
def rolling_zscore(close, window):
    s = pd.Series(close.ravel()) if close.ndim == 1 else pd.DataFrame(close)
    mean = s.rolling(window).mean()
    std = s.rolling(window).std()
    return ((s - mean) / std).to_numpy()

ZSCORE = vbt.IndicatorFactory(
    class_name="ZScore",
    short_name="zs",
    input_names=["close"],
    param_names=["window"],
    output_names=["zscore"],
).from_apply_func(rolling_zscore, window=20)

zs = ZSCORE.run(close, window=[10, 20, 60])
entries = zs.zscore_below(-2.0).vbt.signals.fshift(1)
exits = zs.zscore_above(0.0).vbt.signals.fshift(1)
```

The generated class automatically provides `zscore_above`, `zscore_below`,
`zscore_crossed_above`, `zscore_crossed_below` and `zscore_stats`.

## Recipe 8 — Wrapping TA-Lib and pandas-ta

```python
ADX = vbt.IndicatorFactory.from_talib("ADX")
adx = ADX.run(ohlcv["High"], ohlcv["Low"], ohlcv["Close"], timeperiod=[14, 28])

SUPER = vbt.IndicatorFactory.from_pandas_ta("supertrend")
st = SUPER.run(ohlcv["High"], ohlcv["Low"], ohlcv["Close"], length=10, multiplier=3.0)

print(vbt.IndicatorFactory.get_talib_indicators()[:20])
```

## Recipe 9 — Inspect what actually happened

```python
trades = pf.trades.records_readable
print(trades.sort_values("PnL").head(10))          # the ten worst trades
print(pf.trades.win_rate(), pf.trades.profit_factor(), pf.trades.expectancy())

dd = pf.drawdowns.records_readable
print(dd.sort_values("Drawdown").head(5))

print(pf.positions.records_readable["Size"].describe())
```

If the ten worst trades explain most of the loss and the ten best explain most of the
gain, the strategy is a small number of events with a lot of noise around them.
Compute how the result changes with those events removed before believing it.

## Recipe 10 — Random benchmark for the null

```python
rand_pf = vbt.Portfolio.from_random_signals(
    close, n=int(entries.sum()), seed=list(range(200)),
    size=1.0, size_type="percent", freq="1d",
)
null = rand_pf.sharpe_ratio()
observed = pf.sharpe_ratio()
pval = (null >= observed).mean()
print(f"observed {observed:.3f}, random median {null.median():.3f}, empirical p {pval:.3f}")
```

Matching the trade count keeps the comparison fair. This is the cheapest reality
check in the whole library and it disqualifies a surprising number of strategies.
