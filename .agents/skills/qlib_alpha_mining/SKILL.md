---
name: qlib-alpha-mining
description: "Mine and evaluate cross-sectional alpha with Microsoft Qlib: the expression operator set, Alpha158 and Alpha360 handlers, processors, model zoo, qrun workflow YAML, recorders and IC analysis."
---

# Qlib Alpha Mining & Ranking

Microsoft Qlib is the cross-sectional alpha engine of this suite. Use it when the
question is *"which names, ranked how, at what horizon"* rather than *"when do I
enter this one instrument"*. Qlib's opinionated shape is: an expression engine over
point-in-time bars, a `DataHandlerLP` that separates inference from learning
processing, a model that predicts a score per (datetime, instrument), and recorders
that turn that score into an information coefficient and a portfolio backtest.

Repository: `qlib/`. Import name `qlib`, distribution `pyqlib`.

## When to reach for Qlib

| Use Qlib | Use something else |
|---|---|
| Ranking a universe of hundreds of names daily | Single-instrument timing → `vectorbt-backtest` |
| Formulaic factor libraries (Alpha158/360) | Bar-by-bar order logic → `lean-algorithm-builder` |
| IC / Rank IC evaluation of a signal | Full research methodology → `ml-for-trading` |
| Nested daily→intraday execution simulation | Quick parameter sweeps → `vectorbt-backtest` |

## The five-step loop

### 1. Initialise

```python
import qlib
from qlib.constant import REG_CN, REG_US

qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region=REG_CN)
```

`region` is not cosmetic. It sets `trade_unit`, `limit_threshold` and `deal_price`
defaults (CN: 100 / 0.095 / close; US: 1 / None / close; TW: 1000 / 0.1 / close).
Getting the region wrong silently changes what a backtest is allowed to trade.

### 2. Build the dataset

```python
from qlib.contrib.data.handler import Alpha158
from qlib.data.dataset import DatasetH

handler = Alpha158(
    instruments="csi300",
    start_time="2010-01-01", end_time="2020-12-31",
    fit_start_time="2010-01-01", fit_end_time="2016-12-31",   # normalisation window
)
dataset = DatasetH(handler, segments={
    "train": ("2010-01-01", "2016-12-31"),
    "valid": ("2017-01-01", "2018-12-31"),
    "test":  ("2019-01-01", "2020-12-31"),
})
```

**The fit window is the leakage control.** `RobustZScoreNorm` and `ZScoreNorm` are
fitted on `fit_start_time`..`fit_end_time` only. If you let it default to the whole
sample you have leaked the test distribution into training. `check_transform_proc`
injects those windows for you; do not bypass it.

Alpha158 gives 158 fields from three groups: `kbar` (9 candle-shape ratios),
`price` (OPEN0/HIGH0/LOW0/VWAP0 normalised by close) and `rolling` (28 operator
families over windows 5/10/20/30/60). Alpha360 gives the raw 60-day lookback tensor:
`CLOSE0..59`, `OPEN`, `HIGH`, `LOW`, `VWAP`, `VOLUME`, each normalised by the latest
close or volume. Alpha158 suits tree models; Alpha360 suits sequence models.

Default label for both: `Ref($close, -2)/Ref($close, -1) - 1`. That is **the return
from tomorrow's close to the day after**, not today's. It assumes you trade on the
next bar, which is the correct default; if you change it, change the backtest's
`deal_price` to match or you will book a return you could not have captured.

### 3. Train

```python
from qlib.contrib.model.gbdt import LGBModel

model = LGBModel(loss="mse", learning_rate=0.05, num_leaves=64,
                 max_depth=8, num_threads=8, early_stopping_rounds=50)
model.fit(dataset)
pred = model.predict(dataset, segment="test")
```

`LGBModel`, `XGBModel`, `CatBoostModel`, `LinearModel` and `DEnsembleModel` need no
deep-learning stack. Every `pytorch_*` model requires torch, which is **not** a core
Qlib dependency. The `_ts` variants (`pytorch_lstm_ts`, `pytorch_gats_ts`, …) consume
a `TSDatasetH`, not a `DatasetH` — passing the wrong one fails at fit time.

### 4. Record

```python
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, SigAnaRecord, PortAnaRecord

with R.start(experiment_name="alpha158_lgb"):
    model.fit(dataset)
    R.save_objects(trained_model=model)
    rec = R.get_recorder()
    SignalRecord(model, dataset, rec).generate()      # pred.pkl, label.pkl
    SigAnaRecord(rec).generate()                       # IC, ICIR, Rank IC, Rank ICIR
    PortAnaRecord(rec, port_analysis_config).generate()
```

`SigAnaRecord` is the honest gate. If Rank IC is not materially positive and stable
across the test window, the portfolio backtest that follows is decoration. Read the
IC series, not just its mean — a mean of 0.03 driven by two months is not a signal.

### 5. Backtest

```python
port_analysis_config = {
    "strategy": {
        "class": "TopkDropoutStrategy",
        "module_path": "qlib.contrib.strategy.signal_strategy",
        "kwargs": {"signal": (model, dataset), "topk": 50, "n_drop": 5},
    },
    "backtest": {
        "start_time": "2019-01-01", "end_time": "2020-12-31",
        "account": 100_000_000, "benchmark": "SH000300",
        "exchange_kwargs": {
            "limit_threshold": 0.095,
            "deal_price": "close",
            "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5,
        },
    },
}
```

`open_cost` / `close_cost` / `min_cost` are **not optional**. A Qlib backtest with
zero costs is rejected by this suite. `n_drop` controls turnover directly: a
`topk=50, n_drop=5` book turns over roughly 10% a day, which at 20 bps round trip
costs about 5% a year before you have earned anything.

## Running from YAML

`qrun path/to/workflow_config.yaml` is the reproducible entry point. A real template
lives at `qlib/examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml`.
Sections: `qlib_init`, YAML anchors for `market`/`benchmark`/`data_handler_config`,
`port_analysis_config`, and `task` holding `model`, `dataset` and the `record` list.
Prefer YAML over notebook code for anything you intend to re-run: `qrun` renders
Jinja, applies the `sys` path section, initialises Qlib and calls
`qlib.model.trainer.task_train`.

## Guards specific to Qlib

1. **Never fit processors on the full sample.** Set `fit_start_time`/`fit_end_time`
   to the training segment.
2. **`CSZScoreNorm` on the label is cross-sectional.** It removes the market factor
   from your target. That is usually what you want for ranking, but it means your IC
   measures relative, not absolute, skill.
3. **`limit_threshold` models limit-up/limit-down.** Setting it to `None` in a CN
   backtest lets you trade names nobody could have traded.
4. **Expression `Ref` is a lookback, negative `Ref` is a look-forward.** `Ref($close, -2)`
   is legitimate only inside a *label*. Seeing a negative `Ref` inside a feature is a
   lookahead bug — flag it immediately.
5. **`DataHandlerLP` has two data keys.** `DK_I` (infer) and `DK_L` (learn) can differ.
   If you evaluate on `DK_L` you are scoring against a processed label.

## References

- API surface, operators, model zoo, recorders: [api-reference.md](references/api-reference.md)
- End-to-end code recipes: [recipes.md](references/recipes.md)
- Auto-generated repository map: [project-structure.md](references/project-structure.md)
- Auto-generated dependency map: [tech-stacks.md](references/tech-stacks.md)

## Related skills

`alpha-research-workflow` for the methodology around the signal, `backtest-risk-audit`
before you believe any of these numbers, `portfolio-construction-risk` to replace
`TopkDropoutStrategy` with a real allocator, `execution-costs-microstructure` to
calibrate `open_cost`/`close_cost` to your venue.
