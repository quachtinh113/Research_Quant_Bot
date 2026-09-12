# Qlib Recipes

Runnable patterns. Each one assumes `qlib.init(...)` has already been called.

## Recipe 1 — Minimal end-to-end run in code

```python
import qlib
from qlib.constant import REG_CN
from qlib.contrib.data.handler import Alpha158
from qlib.contrib.model.gbdt import LGBModel
from qlib.data.dataset import DatasetH
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, SigAnaRecord, PortAnaRecord

qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region=REG_CN)

TRAIN = ("2010-01-01", "2016-12-31")
VALID = ("2017-01-01", "2018-12-31")
TEST = ("2019-01-01", "2020-12-31")

handler = Alpha158(
    instruments="csi300",
    start_time=TRAIN[0], end_time=TEST[1],
    fit_start_time=TRAIN[0], fit_end_time=TRAIN[1],
)
dataset = DatasetH(handler, segments={"train": TRAIN, "valid": VALID, "test": TEST})

model = LGBModel(
    loss="mse", learning_rate=0.05, num_leaves=64, max_depth=8,
    colsample_bytree=0.8, subsample=0.9, lambda_l1=100, lambda_l2=200,
    num_threads=8, early_stopping_rounds=50, num_boost_round=1000,
)

port_analysis_config = {
    "strategy": {
        "class": "TopkDropoutStrategy",
        "module_path": "qlib.contrib.strategy.signal_strategy",
        "kwargs": {"signal": (model, dataset), "topk": 50, "n_drop": 5},
    },
    "backtest": {
        "start_time": TEST[0], "end_time": TEST[1],
        "account": 100_000_000, "benchmark": "SH000300",
        "exchange_kwargs": {
            "limit_threshold": 0.095, "deal_price": "close",
            "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5,
        },
    },
}

with R.start(experiment_name="alpha158_lgb"):
    model.fit(dataset)
    R.save_objects(trained_model=model)
    recorder = R.get_recorder()
    SignalRecord(model, dataset, recorder).generate()
    SigAnaRecord(recorder).generate()
    PortAnaRecord(recorder, port_analysis_config, "day").generate()
    print("recorder id:", recorder.id)
```

## Recipe 2 — A custom formulaic factor set

Skip `Alpha158` when you want to control every field. `QlibDataLoader` takes
`(expressions, names)` tuples per group.

```python
from qlib.data.dataset.handler import DataHandlerLP
from qlib.data.dataset.loader import QlibDataLoader
from qlib.data.dataset.processor import (
    CSRankNorm, CSZScoreNorm, DropnaLabel, Fillna, ProcessInf, RobustZScoreNorm,
)

FEATURES = [
    "($close - Mean($close, 20)) / Std($close, 20)",
    "$close / Ref($close, 5) - 1",
    "$close / Ref($close, 20) - 1",
    "Std(Log($close / Ref($close, 1)), 20)",
    "Corr($close, Log($volume + 1), 10)",
    "($high - $low) / $close",
    "Mean($volume, 5) / (Mean($volume, 60) + 1e-12)",
    "Rsquare($close, 20)",
    "Resi($close, 20) / $close",
]
NAMES = ["ZS20", "MOM5", "MOM20", "VOL20", "PVCORR10", "RANGE", "VRATIO", "R2_20", "RESID20"]
LABEL = (["Ref($close, -2)/Ref($close, -1) - 1"], ["LABEL0"])

FIT = ("2010-01-01", "2016-12-31")

handler = DataHandlerLP(
    instruments="csi300",
    start_time="2010-01-01", end_time="2020-12-31",
    data_loader=QlibDataLoader(config={"feature": (FEATURES, NAMES), "label": LABEL}),
    infer_processors=[
        ProcessInf(),
        RobustZScoreNorm(fit_start_time=FIT[0], fit_end_time=FIT[1], clip_outlier=True),
        Fillna(),
    ],
    learn_processors=[DropnaLabel(), CSZScoreNorm(fields_group="label")],
    process_type=DataHandlerLP.PTYPE_A,
)
```

Every feature above uses only non-negative `Ref` offsets. The single negative `Ref`
is in the label, which is where it belongs.

## Recipe 3 — Score a factor before you model it

Do this before training anything. If a factor has no standalone IC, a model will
mostly learn to ignore it.

```python
import pandas as pd
from qlib.data import D
from qlib.contrib.eva.alpha import calc_ic

df = D.features(
    D.instruments("csi300"),
    ["($close - Mean($close, 20)) / Std($close, 20)", "Ref($close, -2)/Ref($close, -1) - 1"],
    start_time="2017-01-01", end_time="2020-12-31",
)
df.columns = ["factor", "label"]
df = df.dropna()

ic, rank_ic = calc_ic(df["factor"], df["label"])
summary = pd.DataFrame({
    "IC mean": [ic.mean()], "IC std": [ic.std()],
    "ICIR": [ic.mean() / ic.std()],
    "Rank IC mean": [rank_ic.mean()],
    "Rank ICIR": [rank_ic.mean() / rank_ic.std()],
    "positive rate": [(rank_ic > 0).mean()],
})
print(summary.to_string(index=False))
print(rank_ic.resample("YE").mean())   # stability across years matters more than the mean
```

Reading guide: Rank ICIR above roughly 0.3 annualised is worth pursuing, a positive
rate near 0.5 with a decent mean means a handful of days carry everything, and any
year with the opposite sign is a regime warning, not noise to average away.

## Recipe 4 — Workflow YAML for `qrun`

```yaml
qlib_init:
  provider_uri: "~/.qlib/qlib_data/cn_data"
  region: cn

market: &market csi300
benchmark: &benchmark SH000300

data_handler_config: &data_handler_config
  start_time: 2010-01-01
  end_time: 2020-12-31
  fit_start_time: 2010-01-01
  fit_end_time: 2016-12-31
  instruments: *market

port_analysis_config: &port_analysis_config
  strategy:
    class: TopkDropoutStrategy
    module_path: qlib.contrib.strategy.signal_strategy
    kwargs:
      signal: <PRED>
      topk: 50
      n_drop: 5
  backtest:
    start_time: 2019-01-01
    end_time: 2020-12-31
    account: 100000000
    benchmark: *benchmark
    exchange_kwargs:
      limit_threshold: 0.095
      deal_price: close
      open_cost: 0.0005
      close_cost: 0.0015
      min_cost: 5

task:
  model:
    class: LGBModel
    module_path: qlib.contrib.model.gbdt
    kwargs:
      loss: mse
      learning_rate: 0.05
      num_leaves: 64
      max_depth: 8
      lambda_l1: 100
      lambda_l2: 200
      num_threads: 8
  dataset:
    class: DatasetH
    module_path: qlib.data.dataset
    kwargs:
      handler:
        class: Alpha158
        module_path: qlib.contrib.data.handler
        kwargs: *data_handler_config
      segments:
        train: [2010-01-01, 2016-12-31]
        valid: [2017-01-01, 2018-12-31]
        test: [2019-01-01, 2020-12-31]
  record:
    - class: SignalRecord
      module_path: qlib.workflow.record_temp
      kwargs: {model: <MODEL>, dataset: <DATASET>}
    - class: SigAnaRecord
      module_path: qlib.workflow.record_temp
      kwargs: {ana_long_short: True, ann_scaler: 252}
    - class: PortAnaRecord
      module_path: qlib.workflow.record_temp
      kwargs: {config: *port_analysis_config}
```

Run it with `qrun workflow_config.yaml`.

## Recipe 5 — Read results back out of the recorder

```python
from qlib.workflow import R

recorder = R.get_recorder(recorder_id="<id>", experiment_name="alpha158_lgb")
pred = recorder.load_object("pred.pkl")
label = recorder.load_object("label.pkl")
ic = recorder.load_object("sig_analysis/ic.pkl")
metrics = recorder.list_metrics()
print({k: v for k, v in metrics.items() if "IC" in k or "Rank" in k})

report, positions = recorder.load_object("portfolio_analysis/report_normal_1day.pkl"), None
print(report[["return", "bench", "cost", "turnover"]].describe())
```

`report["cost"]` against `report["return"]` is the single most informative ratio in a
Qlib backtest. If cumulative cost is the same order of magnitude as cumulative excess
return, the strategy is a fee-generation machine.

## Recipe 6 — Sweep turnover honestly

```python
import itertools
import pandas as pd

rows = []
for topk, n_drop in itertools.product([30, 50, 100], [1, 5, 10]):
    cfg = dict(port_analysis_config)
    cfg["strategy"]["kwargs"].update(topk=topk, n_drop=n_drop)
    with R.start(experiment_name=f"sweep_k{topk}_d{n_drop}"):
        rec = R.get_recorder()
        SignalRecord(model, dataset, rec).generate()
        PortAnaRecord(rec, cfg, "day").generate()
        m = rec.list_metrics()
        rows.append({"topk": topk, "n_drop": n_drop, **m})

sweep = pd.DataFrame(rows)
```

Every row of that table is a trial. Record the count — `backtest-risk-audit` needs
it to deflate the best Sharpe you find. Nine configurations means the best one is
expected to look good by luck alone; report the median as well as the maximum.

## Recipe 7 — Nested daily-to-intraday execution

When daily rebalancing hides the execution cost, nest an intraday executor under the
daily strategy so orders are filled by TWAP over the session rather than at the close.

```python
from qlib.backtest import backtest
from qlib.contrib.strategy import TopkDropoutStrategy

executor_config = {
    "class": "NestedExecutor",
    "module_path": "qlib.backtest.executor",
    "kwargs": {
        "time_per_step": "day",
        "inner_executor": {
            "class": "SimulatorExecutor",
            "module_path": "qlib.backtest.executor",
            "kwargs": {"time_per_step": "30min", "generate_portfolio_metrics": True},
        },
        "inner_strategy": {
            "class": "TWAPStrategy",
            "module_path": "qlib.contrib.strategy.rule_strategy",
        },
        "track_data": True,
    },
}
```

See `qlib/examples/nested_decision_execution/` for a complete configuration.
