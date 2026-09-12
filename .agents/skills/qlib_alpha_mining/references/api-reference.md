# Qlib API Reference

Verified against the checkout in `qlib/`. Paths are relative to that directory.

## 1. Initialisation and configuration

| Symbol | Location | Notes |
|---|---|---|
| `qlib.init(default_conf="client", **kwargs)` | `qlib/__init__.py` | merges kwargs into `QlibConfig` |
| `qlib.init_from_yaml_conf`, `qlib.auto_init` | `qlib/__init__.py` | YAML and auto-discovery entry points |
| `QlibConfig`, singleton `C`, `DataPathManager` | `qlib/config.py` | region defaults live at `config.py:316` |
| `REG_CN`, `REG_US`, `REG_TW`, `EPS`, `INF`, `ONE_DAY`, `ONE_MIN` | `qlib/constant.py` | |

Common `init` kwargs: `provider_uri` (str, Path, or `{freq: uri}`), `region`,
`mount_path`, `auto_mount`, `expression_cache`, `dataset_cache`, `redis_host`,
`redis_port`, `kernels`, `logging_level`, `exp_manager`, `custom_ops`,
`clear_mem_cache=True`, `skip_if_reg=False`.

Region defaults:

| Region | trade_unit | limit_threshold | deal_price |
|---|---:|---:|---|
| CN | 100 | 0.095 | close |
| US | 1 | None | close |
| TW | 1000 | 0.1 | close |

## 2. Expression engine — `qlib/data/ops.py`

Registered into `Operators` by `register_all_ops(C)`.

| Group | Operators |
|---|---|
| Base classes | `ExpressionOps`, `ElemOperator`, `NpElemOperator`, `PairOperator`, `NpPairOperator`, `Rolling`, `PairRolling` |
| Element-wise | `Abs`, `Sign`, `Log`, `Mask`, `Not`, `ChangeInstrument` |
| Arithmetic | `Power`, `Add`, `Sub`, `Mul`, `Div`, `Greater`, `Less` |
| Comparison / logic | `Gt`, `Ge`, `Lt`, `Le`, `Eq`, `Ne`, `And`, `Or`, ternary `If` |
| Rolling | `Ref`, `Mean`, `Sum`, `Std`, `Var`, `Skew`, `Kurt`, `Max`, `Min`, `IdxMax`, `IdxMin`, `Quantile`, `Med`, `Mad`, `Rank`, `Count`, `Delta`, `Slope`, `Rsquare`, `Resi`, `WMA`, `EMA` |
| Pair rolling | `Corr`, `Cov` |
| Resampling | `TResample` |
| Point-in-time | `P`, `PRef` (`qlib/data/pit.py`) |
| Leaves | `Feature`, `PFeature` (`qlib/data/base.py`) |

Fields are `$close`, `$open`, `$high`, `$low`, `$volume`, `$vwap`, `$factor`.

Idiomatic expressions:

```text
($close - Mean($close, 20)) / Std($close, 20)      # 20-day z-score
Ref($close, -5) / $close - 1                        # forward 5-day return (LABEL ONLY)
Corr($close, Log($volume + 1), 10)                  # price-volume coupling
Rank($close / Ref($close, 20) - 1)                  # cross-sectional momentum rank
Resi($close, 10) / $close                           # residual from a 10-day linear fit
```

`Ref(x, n)` with `n > 0` looks back. `Ref(x, -n)` looks **forward** and is legal only
inside a label expression.

## 3. Data layer

Providers in `qlib/data/data.py`: abstract `CalendarProvider`, `InstrumentProvider`,
`FeatureProvider`, `PITProvider`, `ExpressionProvider`, `DatasetProvider`; local
implementations `LocalCalendarProvider`, `LocalInstrumentProvider`,
`LocalFeatureProvider`, `LocalPITProvider`, `LocalExpressionProvider`,
`LocalDatasetProvider`; client variants `ClientCalendarProvider`,
`ClientInstrumentProvider`, `ClientDatasetProvider`; facades `BaseProvider`,
`LocalProvider`, `ClientProvider`. `register_all_wrappers(C)` binds the `D` facade.

Storage: `qlib/data/storage/file_storage.py`, `storage.py`. Native rolling and
expanding kernels are Cython: `qlib/data/_libs/rolling.pyx`, `expanding.pyx`.

### Dataset stack

| Class | Location | Key parameters |
|---|---|---|
| `Dataset` | `qlib/data/dataset/__init__.py` | base |
| `DatasetH` | same | `handler`, `segments: {name: (start, end)}`, `fetch_kwargs` |
| `TSDataSampler` | same | windowed sampler used by sequence models |
| `TSDatasetH` | same | `step_len=DEFAULT_STEP_LEN`, `flt_col` |
| `DataHandlerABC`, `DataHandler` | `handler.py` | |
| `DataHandlerLP` | `handler.py` | `instruments`, `start_time`, `end_time`, `data_loader`, `infer_processors`, `learn_processors`, `shared_processors`, `process_type=PTYPE_A`, `drop_raw=False` |

Data keys: `DK_R` (raw), `DK_I` (infer), `DK_L` (learn).
Process types: `PTYPE_I = "independent"`, `PTYPE_A = "append"`.

Loaders in `loader.py`: `DataLoader`, `DLWParser`, `QlibDataLoader`,
`StaticDataLoader`, `NestedDataLoader`, `DataLoaderDH`.

### Processors — `qlib/data/dataset/processor.py`

`Processor`, `DropnaProcessor`, `DropnaLabel`, `DropCol`, `FilterCol`, `TanhProcess`,
`ProcessInf`, `Fillna`, `MinMaxNorm`, `ZScoreNorm`,
`RobustZScoreNorm(fit_start_time, fit_end_time, fields_group=None, clip_outlier=True)`,
`CSZScoreNorm(fields_group=None, method="zscore")`, `CSRankNorm`, `CSZFillna`,
`HashStockFormat`, `TimeRangeFlt`.

`ZScoreNorm` and `RobustZScoreNorm` are **time-series** normalisers fitted on a
window. `CSZScoreNorm` and `CSRankNorm` are **cross-sectional** and fitted per date,
so they cannot leak across time but do remove the market factor.

## 4. Alpha158 and Alpha360

Handlers: `qlib/contrib/data/handler.py` → `Alpha158`, `Alpha158vwap`, `Alpha360`,
`Alpha360vwap`, all `DataHandlerLP`.
Loaders: `qlib/contrib/data/loader.py` → `Alpha158DL`, `Alpha360DL`, both
`QlibDataLoader` with a static `get_feature_config(...)`.

Shared constructor: `instruments="csi500"`, `start_time`, `end_time`, `freq="day"`,
`infer_processors`, `learn_processors`, `fit_start_time`, `fit_end_time`,
`filter_pipe=None`, `inst_processors=None`. `Alpha158` additionally takes
`process_type=DataHandlerLP.PTYPE_A`.

Defaults:
- `_DEFAULT_LEARN_PROCESSORS = [DropnaLabel, CSZScoreNorm(fields_group="label")]`
- `_DEFAULT_INFER_PROCESSORS = [ProcessInf, ZScoreNorm, Fillna]` (Alpha360 uses these;
  Alpha158 defaults `infer_processors` to `[]`)

Label for both: `["Ref($close, -2)/Ref($close, -1) - 1"] -> ["LABEL0"]`.

**Alpha158 field groups**

| Group | Count | Fields |
|---|---:|---|
| `kbar` | 9 | `KMID, KLEN, KMID2, KUP, KUP2, KLOW, KLOW2, KSFT, KSFT2` |
| `price` | 4 | `OPEN0, HIGH0, LOW0, VWAP0` (raw price ÷ `$close`) |
| `rolling` | 145 | 29 families × windows `[5,10,20,30,60]` |

Rolling families: `ROC, MA, STD, BETA, RSQR, RESI, MAX, MIN, QTLU, QTLD, RANK, RSV,
IMAX, IMIN, IMXD, CORR, CORD, CNTP, CNTN, CNTD, SUMP, SUMN, SUMD, VMA, VSTD, WVMA,
VSUMP, VSUMN, VSUMD`. Names carry the window: `MA20`, `CORR60`.

**Alpha360**: 6 × 60 = 360 fields. `CLOSE{i}, OPEN{i}, HIGH{i}, LOW{i}, VWAP{i}` are
`Ref($x, i)/$close`; `VOLUME{i}` is `Ref($volume, i)/($volume + 1e-12)`; `i` runs 59→0,
so `CLOSE0` and `VOLUME0` normalise to 1.

## 5. Model zoo — `qlib/contrib/model/`

No deep-learning dependency:

| File | Class |
|---|---|
| `gbdt.py` | `LGBModel(ModelFT, LightGBMFInt)` |
| `xgboost.py` | `XGBModel` |
| `catboost_model.py` | `CatBoostModel` |
| `linear.py` | `LinearModel` |
| `double_ensemble.py` | `DEnsembleModel` |
| `highfreq_gdbt_model.py` | `HFLGBModel` |

Torch required: `pytorch_nn.py` (`DNNModelPytorch`), `pytorch_lstm[_ts].py` (`LSTM`),
`pytorch_gru[_ts].py` (`GRU`), `pytorch_alstm[_ts].py` (`ALSTM`),
`pytorch_gats[_ts].py` (`GATs`), `pytorch_transformer[_ts].py` (`TransformerModel`),
`pytorch_localformer[_ts].py` (`LocalformerModel`), `pytorch_tcn[_ts].py` (`TCN`),
`pytorch_tcts.py` (`TCTS`), `pytorch_tabnet.py` (`TabnetModel`), `pytorch_sfm.py`
(`SFM`), `pytorch_adarnn.py` (`ADARNN`), `pytorch_add.py` (`ADD`), `pytorch_hist.py`
(`HIST`), `pytorch_igmtf.py` (`IGMTF`), `pytorch_krnn.py` (`KRNN`),
`pytorch_sandwich.py` (`Sandwich`), `pytorch_tra.py` (`TRAModel`),
`pytorch_general_nn.py` (`GeneralPTNN`). Helpers: `tcn.py` (`TemporalConvNet`),
`pytorch_utils.py`. TFT lives only under `examples/benchmarks/TFT/`.

Model bases: `qlib/model/base.py` → `BaseModel`, `Model`, `ModelFT`.
Interpretability: `qlib/model/interpret/base.py` → `FeatureInt`, `LightGBMFInt`.
Risk models: `qlib/model/riskmodel/` → `base.py`, `shrink.py`, `structured.py`, `poet.py`.

## 6. Workflow and recorders

`qlib/workflow/__init__.py` defines `QlibRecorder(exp_manager)` and the global `R`.
Methods: `start` (context manager), `start_exp`, `end_exp`, `get_exp`, `get_recorder`,
`list_experiments`, `list_recorders`, `save_objects(local_path=None, artifact_path=None, **kwargs)`,
`load_object(name)`, `log_params`, `log_metrics(step=None, **kwargs)`, `log_artifact`,
`download_artifact`, `set_tags`, `set_uri`, `uri_context`, `search_records`,
`delete_exp`, `delete_recorder`. Backed by MLflow through `exp.py`, `expm.py`,
`recorder.py`.

`qrun` is `qlib.cli.run:run`, declared in `pyproject.toml [project.scripts]`.

Recorders — `qlib/workflow/record_temp.py`:

| Class | Produces |
|---|---|
| `RecordTemp` | base |
| `SignalRecord(model, dataset, recorder)` | `pred.pkl`, `label.pkl` |
| `ACRecordTemp(recorder, skip_existing=False)` | artifact-checking base |
| `SigAnaRecord(recorder, ana_long_short=False, ann_scaler=252, label_col=0, skip_existing=False)` | `IC`, `ICIR`, `Rank IC`, `Rank ICIR`, `ic.pkl`, `ric.pkl` |
| `PortAnaRecord(recorder, config=None, risk_analysis_freq=None, indicator_analysis_freq=None, indicator_analysis_method=None, skip_existing=False)` | portfolio metrics |
| `HFSignalRecord` | high-frequency signal analysis |
| `MultiPassPortAnaRecord(recorder, pass_num=10, shuffle_init_score=True)` | multi-pass robustness |

Trainers — `qlib/model/trainer.py`: `task_train`, `begin_task_train`, `end_task_train`,
`Trainer`, `TrainerR`, `DelayTrainerR`, `TrainerRM`, `DelayTrainerRM`.

## 7. Backtest and strategies

`qlib/backtest/__init__.py`:

```python
backtest(start_time, end_time, strategy, executor,
         benchmark="SH000300", account=1e9,
         exchange_kwargs={}, pos_type="Position")
    -> Tuple[PORT_METRIC, INDICATOR_METRIC]
```

Also `get_exchange`, `create_account_instance`, `get_strategy_executor`,
`collect_data`, `format_decisions`.

| Module | Classes |
|---|---|
| `executor.py` | `BaseExecutor`, `NestedExecutor`, `SimulatorExecutor` |
| `exchange.py` | `Exchange(freq="day", start_time, end_time, codes="all", deal_price=None, subscribe_fields=[], limit_threshold=None, volume_threshold=None, open_cost=0.0015, close_cost=0.0025, min_cost=5.0, impact_cost=0.0, extra_quote=None, quote_cls=NumpyQuote)` |
| `account.py` | `Account`, `AccumulatedInfo` |
| `position.py` | `BasePosition`, `Position`, `InfPosition` |
| `decision.py` | `Order`, `OrderDir`, `OrderHelper`, `TradeRange`, `IdxTradeRange`, `TradeRangeByTime`, `BaseTradeDecision`, `TradeDecisionWO`, `TradeDecisionWithDetails`, `EmptyTradeDecision` |
| `report.py` | `PortfolioMetrics`, `Indicator` |
| `signal.py` | `Signal`, `SignalWCache`, `ModelSignal` |

Strategies — `qlib/contrib/strategy/`:

- `signal_strategy.py`: `BaseSignalStrategy` (`signal`, `model`, `dataset`,
  `risk_degree=0.95`, `trade_exchange`),
  `TopkDropoutStrategy(*, topk, n_drop, method_sell="bottom", method_buy="top", hold_thresh=1, only_tradable=False, forbid_all_trade_at_limit=True)`,
  `WeightStrategyBase`, `EnhancedIndexingStrategy`
- `cost_control.py`: `SoftTopkStrategy`
- `rule_strategy.py`: `TWAPStrategy`, `SBBStrategyBase`, `SBBStrategyEMA`, `ACStrategy`,
  `RandomOrderStrategy`, `FileOrderStrategy`
- `order_generator.py`: `OrderGenWInteract`, `OrderGenWOInteract`
- `optimizer/`: portfolio optimisers

## 8. Evaluation

`qlib/contrib/eva/alpha.py`:
`calc_ic(pred, label, date_col="datetime", dropna=False) -> (ic, rank_ic)`,
`calc_all_ic`, `calc_long_short_return`, `calc_long_short_prec`, `pred_autocorr`,
`pred_autocorr_all`.

`qlib/contrib/evaluate.py`:
`risk_analysis(r, N=None, freq="day", mode="sum"|"product")` returning mean, std,
annualized_return, information_ratio and max_drawdown; `indicator_analysis(df, method="mean")`;
`backtest_daily(...)`; `long_short_backtest(...)`.

Plotting: `qlib/contrib/report/analysis_position/` (`report.py`, `risk_analysis.py`,
`score_ic.py`, `cumulative_return.py`, `rank_label.py`) and
`analysis_model/analysis_model_performance.py`.

## 9. Reinforcement learning and high frequency

`qlib/rl/`: `simulator.py` (`Simulator`), `interpreter.py` (`Interpreter`,
`StateInterpreter`, `ActionInterpreter`), `reward.py`, `aux_info.py`, `seed.py`;
`trainer/` (`Trainer`, `TrainingVessel`, callbacks `EarlyStopping`, `Checkpoint`,
`MetricsWriter`, `api.py` `train`/`backtest`); `utils/` (`env_wrapper.py`,
`finite_env.py`, `data_queue.py`, `log.py`); `data/`; `strategy/single_order.py`;
`contrib/` (`train_onpolicy.py`, `backtest.py`, `naive_config_parser.py`).

`qlib/rl/order_execution/`: `SingleAssetOrderExecution`,
`SingleAssetOrderExecutionSimple`, `SAOEState`, `SAOEMetrics`, `SAOEStrategy`,
`SAOEIntStrategy`, `ProxySAOEStrategy`, interpreters
(`FullHistoryStateInterpreter`, `CurrentStepStateInterpreter`,
`CategoricalActionInterpreter`, `TwapRelativeActionInterpreter`), policies
(`PPO`, `DQN`, `AllOne`), rewards (`PAPenaltyReward`, `PPOReward`), `network.py`
(`Recurrent`, `Attention`). Needs the `rl` extra: `tianshou<=0.4.10`, `torch`, `numpy<2.0.0`.

High frequency: `qlib/contrib/data/highfreq_handler.py`, `highfreq_processor.py`,
`highfreq_provider.py`, `qlib/contrib/ops/high_freq.py`,
`qlib/contrib/model/highfreq_gdbt_model.py`; examples in `examples/highfreq/`,
`examples/rl_order_execution/`, `examples/orderbook_data/`,
`examples/nested_decision_execution/`.

## 10. Data acquisition scripts

`scripts/get_data.py` (wraps `qlib.tests.data.GetData` with `fire`),
`scripts/dump_bin.py`, `scripts/dump_pit.py`, `scripts/check_data_health.py`,
`scripts/check_dump_bin.py`, and `scripts/data_collector/` with collectors for
yahoo, crypto, fund, cn_index, us_index, br_index, pit, baostock_5min and crowd_source.

## 11. Environment

`requires-python >= 3.8.0`. Build needs `setuptools`, `setuptools-scm`, `cython`,
`numpy>=1.24.0`; `setup.py` compiles `qlib.data._libs.rolling` and
`qlib.data._libs.expanding`.

Runtime: `pyyaml, numpy, pandas>=1.1, mlflow, filelock>=3.16.0, redis, dill, fire,
ruamel.yaml>=0.17.38, python-redis-lock, tqdm, pymongo, loguru, lightgbm, gym, cvxpy,
joblib, matplotlib, jupyter, nbconvert, pyarrow, pydantic-settings, setuptools-scm`.

Extras: `dev`, `rl`, `lint`, `docs`, `package`, `test`, `analysis`, `client`.
`torch`, `xgboost` and `catboost` are **not** core dependencies — install them
separately for the corresponding models.

## 12. Highest-value files

1. `qlib/qlib/__init__.py`
2. `qlib/qlib/config.py`
3. `qlib/qlib/data/ops.py`
4. `qlib/qlib/data/dataset/handler.py`
5. `qlib/qlib/data/dataset/processor.py`
6. `qlib/qlib/contrib/data/loader.py`
7. `qlib/qlib/contrib/data/handler.py`
8. `qlib/qlib/workflow/record_temp.py`
9. `qlib/qlib/workflow/__init__.py`
10. `qlib/qlib/backtest/__init__.py` and `qlib/qlib/backtest/exchange.py`
11. `qlib/qlib/contrib/strategy/signal_strategy.py`
12. `qlib/examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml` and `qlib/examples/workflow_by_code.py`
