---
name: vectorbt-backtest
description: "Prototype and sweep strategies with vectorbt: Portfolio.from_signals and friends, the indicator factory, signal accessors, walk-forward splitters, stats and returns analytics, and the settings object."
---

# VectorBT Vectorised Simulation & Parameter Grids

vectorbt is the fast-iteration end of this suite. It simulates a whole parameter grid
in one broadcast operation, so it is where a hypothesis goes to be killed cheaply
before anyone writes a LEAN algorithm or a Qlib workflow.

Repository: `vectorbt/`, version **1.1.0**. Note the environment constraints:
`requires-python >= 3.11, < 3.15`, `numpy >= 2.4.6`, `pandas >= 3.0.3, < 4.0`,
`numba >= 0.66`. This release also ships a **Rust backend** alongside Numba, selected
through `vbt.settings['engine']` (`'auto'`, `'numba'`, `'rust'`).

Licence note: the source headers state Apache 2.0 **with the Commons Clause**. That
restricts selling the software itself. Check it before shipping vectorbt inside a
commercial product.

## What vectorbt is and is not

It is a **vectorised** simulator. Every column is an independent parameter
combination evaluated over the same index. That is what makes a 500-combination
sweep take seconds.

It is **not** an event-driven engine. There is no order book, no partial-fill queue
model, and no notion of an order that survives across bars unless you write the
simulation function yourself. Anything where fill mechanics matter belongs in
`lean-algorithm-builder`.

## The core call

```python
import vectorbt as vbt

pf = vbt.Portfolio.from_signals(
    close=close,
    entries=entries,
    exits=exits,
    size=1.0, size_type="percent",
    direction="longonly",
    init_cash=100_000,
    fees=0.0005,          # 5 bps proportional
    fixed_fees=0.0,
    slippage=0.0005,      # 5 bps
    sl_stop=0.05, tp_stop=0.15,
    freq="1d",
)
print(pf.stats())
```

**Defaults you must override.** `vbt.settings['portfolio']` ships with
`init_cash=100.0`, `size=np.inf`, `fees=0.0`, `slippage=0.0`, `freq=None`. A
zero-cost run is the library default, not a considered choice. This suite rejects
any vectorbt result produced with `fees=0` and `slippage=0`.

Set them globally once at the top of a study:

```python
vbt.settings['portfolio']['fees'] = 0.0005
vbt.settings['portfolio']['slippage'] = 0.0005
vbt.settings['portfolio']['freq'] = '1d'
vbt.settings['returns']['year_freq'] = '252 days'
```

`freq` matters more than people expect: without it, Sharpe and every annualised
metric are computed against a guessed period and are quietly wrong.

## Signal timing — the one bug everybody writes

vectorbt executes a signal on the bar where it is `True`, at that bar's `close` by
default. If your signal is computed from that same bar's close, you have just traded
on information you did not have.

```python
fast = vbt.MA.run(close, 10).ma
slow = vbt.MA.run(close, 50).ma

entries = fast.vbt.crossed_above(slow)
exits = fast.vbt.crossed_below(slow)

# Correct: act on the next bar
entries = entries.vbt.signals.fshift(1)
exits = exits.vbt.signals.fshift(1)
```

Alternatively pass `price=open` so the fill happens at the next open. Pick one
convention per project and state it in the code.

## Parameter grids

Indicators broadcast parameters into columns automatically:

```python
fast = vbt.MA.run(close, window=[5, 10, 20, 50], short_name="fast")
slow = vbt.MA.run(close, window=[50, 100, 200], short_name="slow")

entries = fast.ma_crossed_above(slow)      # 4 x 3 = 12 columns
exits = fast.ma_crossed_below(slow)

pf = vbt.Portfolio.from_signals(close, entries, exits,
                                fees=0.0005, slippage=0.0005, freq="1d")
sharpe = pf.sharpe_ratio()
```

Use `param_product=True` inside `.run()` for a Cartesian product of several
parameters, and `Ind.run_combs(..., r=2)` when you want every pair of settings with
shared caching.

**Every column is a trial.** A 12-column sweep means twelve chances for luck. Carry
that number forward: `backtest-risk-audit` uses it to deflate the winner's Sharpe.
vectorbt itself gives you `pf.returns().vbt.returns.deflated_sharpe_ratio(...)` via
the returns accessor.

## Walk-forward, not in-sample

`pf.stats()` on the full sample is a description, not evidence. Split first:

```python
(in_price, in_idx), (out_price, out_idx) = close.vbt.rolling_split(
    n=10, window_len=252 * 3, set_lens=(252,), left_to_right=False,
)
```

`generic/splitters.py` provides `RangeSplitter`, `RollingSplitter` and
`ExpandingSplitter`; `.vbt.split(splitter)` also accepts any scikit-learn
cross-validator, including `TimeSeriesSplit`. Select parameters on the in-sample
slice, report on the out-of-sample slice, and never the other way round.

## Reading the output

`pf.stats()` returns Start, End, Period, Start/End Value, Total Return, Benchmark
Return, Max Gross Exposure, **Total Fees Paid**, Max Drawdown and its duration,
trade counts, Win Rate, Best/Worst Trade, Profit Factor, Expectancy, and the Sharpe,
Calmar, Omega and Sortino ratios.

Read **Total Fees Paid** against **End Value − Start Value** first. If fees are a
large fraction of gross profit, the strategy is a cost story and no amount of
parameter tuning fixes it.

Record objects give the detail: `pf.trades`, `pf.positions`, `pf.orders`,
`pf.drawdowns`, each with `.records_readable` for a DataFrame you can inspect.

## Guards specific to vectorbt

1. **Set `freq`.** Otherwise annualised metrics are meaningless.
2. **Shift signals** or fill at the next open.
3. **Never leave fees and slippage at zero.**
4. **`size=np.inf` is the default** and means "spend everything". Use
   `size_type="percent"` or `"targetpercent"` for anything multi-asset.
5. **Grouping and cash sharing change the meaning of the run.** Without
   `group_by` and `cash_sharing=True`, each column has its own independent cash pot;
   that is a set of single-asset backtests, not a portfolio.
6. **Caching is on by default** for several classes. When you mutate settings between
   runs, check `vbt.settings['caching']` or you will compare against a stale result.

## References

- Full API surface: [api-reference.md](references/api-reference.md)
- Runnable patterns: [recipes.md](references/recipes.md)
- Auto-generated repository map: [project-structure.md](references/project-structure.md)
- Auto-generated dependency map: [tech-stacks.md](references/tech-stacks.md)

## Related skills

`alpha-research-workflow` for what to sweep and why, `backtest-risk-audit` for
deflating the winner, `execution-costs-microstructure` to choose the fee and slippage
numbers, `lean-algorithm-builder` when the prototype survives and needs real fills.
