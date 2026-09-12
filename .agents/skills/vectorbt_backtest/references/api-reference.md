# VectorBT API Reference

Verified against `vectorbt/` at version 1.1.0. Paths are relative to that directory.

## 1. Package map

| Package | Role | Key modules |
|---|---|---|
| `base` | array wrapping, broadcasting, indexing, grouping | `array_wrapper.py` (`ArrayWrapper`), `reshape_fns.py`, `index_fns.py`, `indexing.py`, `column_grouper.py` (`ColumnGrouper`), `combine_fns.py`, `accessors.py` |
| `generic` | generic series ops, stats and plot builders, splitters, drawdowns | `accessors.py`, `nb.py`, `drawdowns.py`, `ranges.py`, `splitters.py`, `stats_builder.py`, `plots_builder.py`, `plotting.py`, `enums.py`, `dispatch.py` |
| `signals` | boolean signal generation and analysis | `accessors.py`, `factory.py` (`SignalFactory`), `generators.py`, `nb.py`, `enums.py` |
| `portfolio` | simulation and performance | `base.py` (`Portfolio`), `nb.py`, `enums.py`, `orders.py`, `trades.py`, `logs.py`, `decorators.py` |
| `indicators` | indicator construction | `factory.py` (`IndicatorFactory`, `IndicatorBase`), `basic.py`, `configs.py`, `nb.py` |
| `records` | record arrays and mapped arrays | `base.py` (`Records`), `mapped_array.py`, `col_mapper.py`, `decorators.py` |
| `data` | data acquisition | `base.py` (`Data`), `custom.py`, `updater.py` (`DataUpdater`) |
| `labels` | supervised-ML label generation | `generators.py`, `nb.py`, `enums.py` |
| `returns` | return metrics | `accessors.py`, `metrics.py`, `nb.py`, `qs_adapter.py` |
| `utils` | infrastructure | `config.py` (`Config`, `Configured`), `decorators.py`, `template.py` (`Sub`, `Rep`, `RepEval`), `params.py`, `datetime_.py`, `schedule_.py`, `figure.py`, `checks.py` |
| `messaging` | `telegram.py` (`TelegramBot`) | |
| top level | `_settings.py`, `_engine.py`, `root_accessors.py`, `ohlcv_accessors.py`, `px_accessors.py`, `_typing.py` | |

`vectorbt/__init__.py` star-imports every subpackage, so `vbt.Portfolio`,
`vbt.IndicatorFactory`, `vbt.YFData` and `vbt.settings` are all top level.

## 2. Accessors — `vectorbt/root_accessors.py`

Registration helpers: `register_series_accessor`, `register_dataframe_accessor`,
`register_series_vbt_accessor`, `register_dataframe_vbt_accessor`. Accessors are
**not cached** — `df.vbt` re-instantiates each time.

| Accessor | Class |
|---|---|
| `.vbt` | `Vbt_SRAccessor` / `Vbt_DFAccessor` |
| `.vbt.signals` | `SignalsSRAccessor` / `SignalsDFAccessor` |
| `.vbt.returns` | `ReturnsSRAccessor` / `ReturnsDFAccessor` |
| `.vbt.ohlc`, `.vbt.ohlcv` | `OHLCVDFAccessor` |
| `.vbt.px` | `PXSRAccessor` / `PXDFAccessor` (plotly express) |

From `BaseAccessor`: `to_2d_array`, `tile`, `repeat`, `broadcast`, `broadcast_to`,
`concat`, `apply_and_concat`, `combine`, `make_symmetric`, `stack_index`, plus
arithmetic and comparison operator overloads.

From `GenericAccessor`: `rolling_std`, `expanding_std`, `ewm_mean`, `ewm_std`,
`rolling_apply`, `expanding_apply`, `groupby_apply`, `resample_apply`,
`apply_and_reduce`, `zscore`, `drawdown()`, `drawdowns`, `to_mapped()`,
`crossed_above(other, wait=0)`, `crossed_below`, `split(splitter, ...)`,
`range_split`, `rolling_split`, `expanding_split`, `plot()`, `stats()`, `plots()`.

## 3. `Portfolio` — `vectorbt/portfolio/base.py`

`class Portfolio(Wrapping, StatsBuilderMixin, PlotsBuilderMixin, metaclass=MetaPortfolio)`.

Constructors: `from_orders`, `from_signals`, `from_holding(close, **kwargs)` (delegates
to `from_signals(close, entries=True, exits=False)`),
`from_random_signals(close, n=None, prob=None, entry_prob=None, exit_prob=None, param_product=False, seed=None, run_kwargs=None, **kwargs)`,
`from_order_func(close, order_func_nb, *order_args, flexible=..., pre_sim_func_nb=..., pre_segment_func_nb=..., post_order_func_nb=..., row_wise=..., use_numba=..., segment_mask=..., ...)`.

### `Portfolio.from_signals` parameters

```text
close, entries=None, exits=None, short_entries=None, short_exits=None,
signal_func_nb=nb.no_signal_func_nb, signal_args=(),
size=None, size_type=None, price=None,
fees=None, fixed_fees=None, slippage=None,
min_size=None, max_size=None, size_granularity=None,
reject_prob=None, lock_cash=None, allow_partial=None, raise_reject=None, log=None,
accumulate=None,
upon_long_conflict=None, upon_short_conflict=None, upon_dir_conflict=None,
upon_opposite_entry=None, direction=None,
val_price=None, open=None, high=None, low=None,
sl_stop=None, sl_trail=None, tp_stop=None,
stop_entry_price=None, stop_exit_price=None, upon_stop_exit=None, upon_stop_update=None,
adjust_sl_func_nb=nb.no_adjust_sl_func_nb, adjust_sl_args=(),
adjust_tp_func_nb=nb.no_adjust_tp_func_nb, adjust_tp_args=(), use_stops=None,
init_cash=None, cash_sharing=None, call_seq=None,
ffill_val_price=None, update_value=None,
max_orders=None, max_logs=None, init_temp_records=None,
seed=None, group_by=None,
broadcast_named_args=None, broadcast_kwargs=None, template_mapping=None,
wrapper_kwargs=None, freq=None, attach_call_seq=None, engine=None, **kwargs
```

Three signal modes: `(entries, exits)` with `direction`; the four-array long/short
form; or a custom `signal_func_nb` with `signal_args`.

### Global defaults — `vectorbt/_settings.py`

| Key | Default |
|---|---|
| `init_cash` | `100.0` |
| `size` | `np.inf` |
| `size_type` | `"amount"` |
| `fees`, `fixed_fees`, `slippage` | `0.0` |
| `min_size` | `1e-8` |
| `call_seq` | `"default"` |
| `cash_sharing` | `False` |
| `accumulate` | `False` |
| `sl_stop`, `tp_stop` | `np.nan` |
| `sl_trail` | `False` |
| `stop_entry_price` | `"close"` |
| `stop_exit_price` | `"stoplimit"` |
| `upon_opposite_entry` | `"reversereduce"` |
| `signal_direction` | `"longonly"` |
| `order_direction` | `"both"` |
| `freq` | `None` |
| `trades_type` | `"exittrades"` |
| `fillna_close` | `True` |
| `attach_call_seq` | `False` |

### Analysis surface

`wrapper`, `regroup(group_by)`, `cash_sharing`, `call_seq()`, `close`,
`get_filled_close()`, `order_records`, `orders`, `logs`, `log_records`,
`entry_trades`, `exit_trades`, `trades`, `positions`, `drawdowns`, `asset_flow()`,
`assets()`, `position_mask()`, `position_coverage()`, `cash_flow()`, `init_cash`,
`cash()`, `asset_value()`, `gross_exposure()`, `net_exposure()`, `value()`,
`total_profit()`, `final_value()`, `total_return()`, `returns()`, `asset_returns()`,
`returns_acc`, `qs`, `benchmark_value()`, `benchmark_returns()`,
`total_benchmark_return()`, `returns_stats()`, `stats()`, `plots()`.

Plotters: `plot_orders`, `plot_trades`, `plot_trade_pnl`, `plot_positions`,
`plot_position_pnl`, `plot_asset_flow`, `plot_cash_flow`, `plot_assets`, `plot_cash`,
`plot_asset_value`, `plot_value`, `plot_cum_returns`, `plot_drawdowns`,
`plot_underwater`, `plot_gross_exposure`, `plot_net_exposure`.

`stats()` rows: Start, End, Period, Start Value, End Value, Total Return [%],
Benchmark Return [%], Max Gross Exposure [%], Total Fees Paid, Max Drawdown [%],
Max Drawdown Duration, Total Trades, Total Closed Trades, Total Open Trades,
Open Trade PnL, Win Rate [%], Best Trade [%], Worst Trade [%], Avg Winning Trade [%],
Avg Losing Trade [%], Avg Winning Trade Duration, Avg Losing Trade Duration,
Profit Factor, Expectancy, Sharpe Ratio, Calmar Ratio, Omega Ratio, Sortino Ratio.
Default `plots()` subplots: `["orders", "trade_pnl", "cum_returns"]`.

### Record classes

| Class | Location | Fields |
|---|---|---|
| `Orders` | `portfolio/orders.py` | `id, col, idx, size, price, fees, side` |
| `Trades(Ranges)` | `portfolio/trades.py` | `id, col, size, entry_idx, entry_price, entry_fees, exit_idx, exit_price, exit_fees, pnl, return, direction, status, parent_id` |
| `EntryTrades`, `ExitTrades`, `Positions` | same | subclasses built via `from_orders` / `from_trades` |
| `Drawdowns(Ranges)` | `generic/drawdowns.py` | `id, col, start_idx, valley_idx, end_idx, peak_val, valley_val, end_val, status` |

`Trades` methods: `winning`, `losing`, `winning_streak`, `losing_streak`,
`win_rate()`, `profit_factor()`, `expectancy()`, `sqn()`, `plot()`, `plot_pnl()`.
`Drawdowns`: `drawdown`, `avg_drawdown()`, `max_drawdown()`, `recovery_return`,
`decline_duration`, `recovery_duration`, `recovery_duration_ratio`,
`active_drawdown()`, `active_recovery()`, `from_ts()`.
`Records` / `MappedArray` shared: `.records_readable`, `.values`, `.apply_mask`,
`.top_n(n)`, `.reduce`, `.to_pd()`, `min/max/mean/median/std/sum/idxmin/idxmax/count/describe/value_counts`.

## 4. Indicators

```python
IndicatorFactory(
    class_name="Indicator", class_docstring="", module_name=__name__,
    short_name=None, prepend_name=True,
    input_names=None, param_names=None, in_output_names=None, output_names=None,
    output_flags=None, custom_output_props=None, attr_settings=None,
    metrics=None, stats_defaults=None, subplots=None, plots_defaults=None,
)
```

Builders:
- `from_custom_func(custom_func, require_input_shape=False, param_settings=None, in_output_settings=None, hide_params=None, hide_default=True, var_args=False, ...)`
- `from_apply_func(apply_func, cache_func=None, pass_packed=False, kwargs_to_args=None, numba_loop=False, pass_seed=False, ...)`
- `from_talib(func_name, init_kwargs=None, **kwargs)` and `get_talib_indicators()`
- `from_pandas_ta(func_name, parse_kwargs=None, init_kwargs=None, **kwargs)` and `get_pandas_ta_indicators()`
- `from_ta(cls_name, init_kwargs=None, **kwargs)`, `get_ta_indicators()`, `find_ta_indicator`

Generated class API: `Ind.run(<inputs>, <params>, short_name=..., hide_params=None, hide_default=True, **kwargs)`.
Extra kwargs reach `run_pipeline`: `param_product=False`, `per_column`, `run_unique`,
`keep_pd`, `to_2d`, `param_settings`. `Ind.run_combs(*args, r=2, comb_func=itertools.combinations, short_names=None, **kwargs)`
returns `r` instances over parameter combinations with shared caching.

Numeric outputs gain `<out>_above/below/equal/crossed_above/crossed_below(other, wait=0)`;
boolean outputs gain `_and/_or/_xor`; every output gains `<out>_stats`.

Built-ins in `indicators/basic.py`:

| Indicator | Short | Inputs | Params | Outputs |
|---|---|---|---|---|
| `MA` | `ma` | close | `window, ewm` | `ma` |
| `MSTD` | `mstd` | close | `window, ewm` | `mstd` |
| `BBANDS` | `bb` | close | `window, ewm, alpha` | `middle, upper, lower` |
| `RSI` | `rsi` | close | `window, ewm` | `rsi` |
| `STOCH` | `stoch` | high, low, close | `k_window, d_window, d_ewm` | `percent_k, percent_d` |
| `MACD` | `macd` | close | `fast_window, slow_window, signal_window, macd_ewm, signal_ewm` | `macd, signal` (+`hist`) |
| `ATR` | `atr` | high, low, close | `window, ewm` | `tr, atr` |
| `OBV` | `obv` | close, volume | — | `obv` |

## 5. Signals — `vectorbt/signals/`

`SignalsAccessor` methods: `generate` (classmethod), `generate_both`,
`generate_exits(exit_choice_func, *args, wait=1, until_next=True, skip_until_exit=False, pick_first=False)`,
`generate_random(shape, n=None, prob=None, pick_first=False, seed=None)`,
`generate_random_both`, `generate_random_exits`,
`generate_stop_exits(ts, stop, trailing=False, entry_wait=1, exit_wait=1, until_next=True, skip_until_exit=False, pick_first=True, chain=False)`,
`generate_ohlc_stop_exits(open, high=None, low=None, close=None, is_open_safe=True, out_dict=None, sl_stop=nan, sl_trail=False, tp_stop=nan, reverse=False, ..., chain=False)`,
`clean()`, `fshift`, `bshift` (`fill_value=False`), ranking helpers `rank`, `pos_rank`,
`partition_pos_rank`, `first`, `nth(n)`, `from_nth(n)`, `nth_index`, `norm_avg_index`,
`between_ranges`, `partition_ranges`, `between_partition_ranges`, `total()`, `rate()`,
`total_partitions()`, `partition_rate()`.

`SignalFactory(IndicatorFactory)` with `mode` in `entries`/`exits`/`both`/`chain`, plus
`from_choice_func(...)`. Generators: `RAND(n)`, `RANDX`, `RANDNX(n)`, `RPROB(prob)`,
`RPROBX`, `RPROBCX`, `RPROBNX(entry_prob, exit_prob)`, `STX`/`STCX` (`stop, trailing`),
`OHLCSTX`/`OHLCSTCX` (`sl_stop, sl_trail, tp_stop, reverse`, in-outputs `stop_price`,
`stop_type`).

## 6. Data layer — `vectorbt/data/`

`Data.download(symbols, tz_localize=None, tz_convert=None, missing_index=None, missing_columns=None, wrapper_kwargs=None, **kwargs)`
loops `download_symbol(symbol, **kwargs)`. Per-symbol kwargs via `symbol_dict`.
`update(**kwargs)` calls `update_symbol` and merges. Also `data`, `symbols`,
`get(column=None)`, `concat(level_name="symbol")`, `plot()`.

| Class | Key download parameters |
|---|---|
| `SyntheticData`, `GBMData` | synthetic paths |
| `YFData` | `period="max", start=None, end=None, ticker_kwargs=None` |
| `BinanceData` | `client=None, interval="1d", start=0, end="now UTC", delay=500, limit=500, show_progress=True` |
| `CCXTData` | `exchange="binance", config=None, timeframe="1d", start=0, end="now UTC", delay=None, limit=500, retries=3, params=None` |
| `AlpacaData` | `timeframe="1d", start=0, end="now UTC", adjustment="all", limit=500, feed=None` |

Credentials come from `settings['data']['binance' | 'ccxt' | 'alpaca']`.
`DataUpdater(data, schedule_manager=None)` with `update()` and `update_every(...)`.

## 7. Returns and splitters

`ReturnsAccessor(obj, benchmark_rets=None, year_freq=None, defaults=None)`, plus
`ReturnsAccessor.from_value(...)`. Metrics, each with a `rolling_*` twin: `daily`,
`annual`, `cumulative`, `total`, `annualized`, `annualized_volatility`,
`calmar_ratio`, `omega_ratio`, `sharpe_ratio`, **`deflated_sharpe_ratio`**,
`downside_risk`, `sortino_ratio`, `information_ratio`, `beta`, `alpha`, `tail_ratio`,
`common_sense_ratio`, `value_at_risk`, `cond_value_at_risk`, `capture`, `up_capture`,
`down_capture`, `drawdown`, `max_drawdown`, `drawdowns`, `resample_total_return`, `qs`.

Defaults from `settings['returns']`: `year_freq="365 days"`, `start_value=0.0`,
`window=10`, `minp=None`, `ddof=1`, `risk_free=0.0`, `levy_alpha=2.0`,
`required_return=0.0`, `cutoff=0.05`. Set `year_freq="252 days"` for daily equities.

`returns/qs_adapter.py` exposes the QuantStats function set as `.qs.<func>`.
`returns/metrics.py` implements `deflated_sharpe_ratio` and `approx_exp_max_sharpe`.

Splitters — `generic/splitters.py`: `BaseSplitter`,
`RangeSplitter.split(X, n=None, range_len=None, min_len=1, start_idxs=None, end_idxs=None)`,
`RollingSplitter.split(X, n=None, window_len=None, min_len=1)`,
`ExpandingSplitter.split(X, n=None, min_len=1)`, helper `split_ranges_into_sets(...)`
with `set_lens` and `left_to_right`. Accessor entry points: `.vbt.split(splitter)`
(accepts scikit-learn cross-validators), `.range_split()`, `.rolling_split()`,
`.expanding_split()`.

## 8. Performance model

There is no chunking module in this version. Performance comes from:

1. **Numba kernels** in each `*/nb.py`.
2. **A Rust backend**: `vectorbt/_engine.py` with `settings['engine']` in
   `('auto', 'numba', 'rust')`, `is_rust_available()`, `resolve_engine(...)`,
   `RustSupport` / `RustConversion` checks, and per-package `dispatch.py`. Most public
   methods accept `engine=None`. The `rust` extra installs `vectorbt-rust==1.1.0`.
3. **Flex indexing** in `base/reshape_fns.py`: `flex_choose_i_and_col_nb`,
   `flex_select_nb`, `flex_select_auto_nb` let scalars and 1-D arrays behave as full
   2-D arrays without materialising them.
4. **Broadcasting**: `broadcast`, `broadcast_to`, `to_1d`, `to_2d`, `tile`, `repeat`.

`vbt.settings` is a `SettingsConfig(Config)` with `set_theme`, `reset_theme`,
`register_templates`, `save()`, `load()`. Top-level keys: `engine`, `numba`, `config`,
`configured`, `caching`, `broadcasting`, `array_wrapper`, `datetime`, `data`,
`plotting`, `stats_builder`, `plots_builder`, `generic`, `ranges`, `drawdowns`,
`ohlcv`, `signals`, `returns`, `qs_adapter`, `records`, `mapped_array`, `orders`,
`trades`, `logs`, `portfolio`, `messaging`.

Caching is governed by `utils/decorators.py`: `cached_property`, `cached_method`,
`custom_property`, `should_cache(...)`, `CacheCondition(instance=, cls=, base_cls=, func=, flags=)`.
`ArrayWrapper`, `ColumnGrouper` and `ColumnMapper` are whitelisted by default.

## 9. Environment

`requires-python >= 3.11, < 3.15`. Core: `numpy>=2.4.6`, `pandas>=3.0.3,<4.0`, `scipy`,
`matplotlib`, `plotly>=4.12.0`, `ipywidgets>=7.0.0`, `anywidget`, `numba>=0.66`,
`dill`, `tqdm`, `dateparser`, `imageio`, `scikit-learn`, `schedule`, `requests`,
`pytz`, `mypy_extensions`.

Extras: `rust` (`vectorbt-rust==1.1.0`), `full` (`TA-Lib`, `yfinance>=0.2.22`,
`python-binance`, `ccxt>=4.0.14`, `alpaca-py`, `ray>=1.4.1`, `ta`,
`pandas-ta-classic`, `python-telegram-bot>=13.4`, `quantstats>=0.0.37`), `test`,
`test-rust`, `docs`, `all`.

Licence headers: Apache 2.0 **with Commons Clause**.

## 10. Highest-value files

1. `vectorbt/portfolio/base.py`
2. `vectorbt/portfolio/nb.py`
3. `vectorbt/portfolio/enums.py`
4. `vectorbt/indicators/factory.py`
5. `vectorbt/indicators/basic.py`
6. `vectorbt/signals/accessors.py`
7. `vectorbt/signals/generators.py` and `vectorbt/signals/factory.py`
8. `vectorbt/generic/accessors.py`
9. `vectorbt/returns/accessors.py`
10. `vectorbt/_settings.py`
11. `vectorbt/base/reshape_fns.py` and `vectorbt/base/array_wrapper.py`
12. `vectorbt/data/custom.py`
13. `vectorbt/_engine.py`
