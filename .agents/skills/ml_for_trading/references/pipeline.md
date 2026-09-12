# ML4T Pipeline Operations

How to actually run and extend a case study without breaking the evidence boundary.

## 1. Set up a writable experiment

Never write into a published `run_log/`.

```bash
cd machine-learning-for-trading

uv run python scripts/verify_installation.py

uv run python scripts/create_experiment.py --cs etfs --output experiments/my_run
export ML4T_OUTPUT_DIR=experiments/my_run          # PowerShell: $env:ML4T_OUTPUT_DIR="experiments/my_run"
```

`create_experiment.py` copies the configuration and points the registry at a fresh
database, so the baseline stays intact and comparable.

## 2. Get data

```bash
uv run python data/download_all.py --free-only --skip-firm-characteristics
uv run python scripts/download_artifacts.py --cs etfs
```

`.env` supplies `EDGAR_IDENTITY`, `FRED_API_KEY`, `QUANDL_API_KEY`, `OANDA_API_KEY`,
`DATABENTO_API_KEY` and the `ALPACA_*` keys. `ML4T_DATA_PATH` relocates the data root.

## 3. Run the stages in order

Always from the repository root.

```bash
uv run python case_studies/etfs/01_feasibility_analysis.py
uv run python case_studies/etfs/02_labels.py
uv run python case_studies/etfs/03_financial_features.py
uv run python case_studies/etfs/05_evaluation.py
uv run python case_studies/etfs/07_gbm.py
uv run python case_studies/etfs/14_backtest.py
uv run python case_studies/etfs/15_portfolio_management.py
uv run python case_studies/etfs/17_costs.py
uv run python case_studies/etfs/20_strategy_analysis.py
```

Stages 18 and 19 touch the holdout. Run them once, when everything else is frozen.

Headless:

```bash
MPLBACKEND=Agg PLOTLY_RENDERER=json uv run python case_studies/etfs/07_gbm.py
```

Testing a notebook:

```bash
uv run pytest tests/test_chapter_notebooks.py -v -k "<notebook_stem>"
```

## 4. `setup.yaml` is the single source of truth

Everything that defines the trading problem lives in
`case_studies/<cs>/config/setup.yaml`: the universe, the rebalance cadence, the
execution assumption, the cost model, the label definition and its buffer, the
walk-forward geometry (`n_splits`, `train_size`, `val_size`) and the sweep grids.

Pinned keys that must not move without a clean run log:
`labels.rebalance_step`, `labels.classification_eval_label`, `universe.cost_feasible`,
`backtest.sweep.htm_cost_cascade.liquid_quantile`, and anything in
`config/backtest/base.yaml`.

Three configuration layers, most specific wins:

1. `case_studies/config/<model_type>/<name>.yaml` — reusable model presets
2. `case_studies/<cs>/config/training/<label>.yaml` — the menu of families for a label
3. `setup.yaml` — the problem definition that binds them

Model families keyed in a training menu: `linear`, `gbm`, `tabular_dl`,
`deep_learning`, `latent_factors`, `causal_dml`.

## 5. Walk-forward splits with purge and embargo

```python
from utils.cv_splits import generate_cv_splits, make_walk_forward_config
from utils.modeling import load_modeling_dataset

mds = load_modeling_dataset(case_study="etfs", label="fwd_21d")
splits = generate_cv_splits(mds, make_walk_forward_config(
    n_splits=8, train_size=756, val_size=252, label_buffer=21, buffer_unit="days",
))
```

`generate_cv_splits` delegates to `ml4t-diagnostic`'s `WalkForwardCV`. The
`label_buffer` is the purge gap: with a 21-day forward label, the last 21 training
observations overlap the validation window and must be dropped, or the model has seen
the answer. `_purge_holdout_touching_validation` enforces the same rule at the holdout
boundary. `normalize_label_buffer` reconciles buffer units.

For the theory and a combinatorial purged implementation, read
`06_strategy_definition/02_cv_foundations.py`, which covers the label buffer and
purging, the feature buffer and embargo, calendar-aware CV, nested walk-forward and
combinatorial purged cross-validation.

Fold machinery: `case_studies/utils/folds.py` (`RawFold`, `prepare_raw_folds`,
`iter_raw_folds`, `prepare_standardized_folds`, `prepare_gbm_folds_from_mds`),
`case_studies/utils/cv_window.py` (`fold_boundaries`,
`assert_variant_folds_are_out_of_sample`, `canonical_window`), and
`utils/modeling.validate_temporal_split_geometry`.

## 6. Evaluate the signal before the strategy

```python
from case_studies.utils.analytics import load_model_ic, load_best_ic_per_family
from case_studies.utils.model_analysis import (
    regime_conditional_ic, common_sample_daily_ic,
    fold_performance_matrix, prediction_bucket_monotonicity, indistinguishable_groups,
)
```

`fold_performance_matrix` is the honest view: a model that wins on average but loses
in three of eight folds has not generalised. `indistinguishable_groups` tells you when
two models differ by less than the noise, which is the signal to stop tuning.
`prediction_bucket_monotonicity` checks that higher predicted scores really do produce
higher realised returns — a model with a good IC but a non-monotone bucket profile is
usually fitting the tails.

Stage 05 writes `evaluation/triage_ledger.parquet` and `evaluation/ic_timeseries.parquet`.

## 7. Backtest and gates

```python
from case_studies.utils.backtest_runner import (
    run_backtest, compute_portfolio_metrics, resolve_periods_per_year, BacktestRunResult,
)
from case_studies.utils.strategy_analysis import (
    gate1_validation_sharpe_geq_zero,
    gate2_holdout_diff_not_excludes_zero_negatively,
    plot_ic_vs_sharpe, plot_sharpe_waterfall, plot_cost_decay,
    plot_equity_drawdown, load_holdout_metrics,
)
```

The two gates encode the verdict rule:

- **Gate 1** — validation Sharpe must be at least zero. Fail here and there is nothing
  to take to the holdout.
- **Gate 2** — the holdout-minus-validation difference must not exclude zero on the
  negative side. A holdout materially worse than validation means the selection was
  fitted to validation noise.

`plot_cost_decay` is the one to look at first. It shows Sharpe as a function of the
cost assumption. A strategy whose Sharpe crosses zero between 5 and 15 basis points is
not a strategy, it is a rebate.

Backtest return series come out through `case_studies/utils/backtest_loaders.py`
(`extract_daily_returns_frame`, `aggregate_timestamped_returns_to_daily`).

## 8. Portfolio construction and risk

```python
from case_studies.utils.allocation import (
    compute_hrp_weights, compute_mvo_weights, compute_risk_parity_weights,
    compute_inverse_vol_weights, compute_conformal_weights,
)
from case_studies.utils.signals import build_target_weights, cross_sectional_percentile_signal
from case_studies.utils.conformal import (
    walk_forward_conformal_coverage, compute_conformal_widths,
    holdout_conformal_embargo_steps, coverage_summary,
)
```

Stages 15, 16 and 17 are portfolio management, risk management and costs. The
allocator is a selection choice like any other, so it is chosen on validation.

## 9. Adding a new case study

1. Copy the directory structure of the closest existing case study.
2. Write `config/setup.yaml` first: universe, cadence, costs, label, walk-forward
   geometry. Nothing else can be decided before this.
3. Add a data loader to `data/` and register it in `data/__init__.py`.
4. Run `01_feasibility_analysis` and be willing to stop there. If the universe cannot
   carry the intended turnover at realistic costs, the case study is finished.
5. Add training menus under `config/training/`, reusing presets from
   `case_studies/config/<model_type>/`.
6. Run stages in order. Let the registry deduplicate: `skip_training_if_complete`
   means re-running is cheap.
7. Touch the holdout once, at stage 18 and 19.

## 10. Notebook conventions

Jupytext percent format. Edit the `.py`, then:

```bash
uv run python scripts/sync_notebooks.py case_studies/etfs/07_gbm.py
uv run python scripts/sync_notebooks.py --check          # detect drift
uv run python scripts/sync_notebooks.py --safe-only      # docs-only, keep outputs
```

Parameterise for shortened runs with a Papermill cell:

```python
# %% tags=["parameters"]
execution_tier = "full"      # "preview" for a reduced run
n_splits = 8
```

Never write `if TEST:`. A code path that only runs in tests is a code path nobody has
validated.

## 11. The OpenMP import order

```python
import lightgbm as lgb        # before sklearn
import xgboost as xgb
from sklearn.linear_model import Ridge
```

Importing scikit-learn first can bind a different OpenMP runtime and cause crashes or
silent single-threading on some platforms. This is a real constraint, not superstition.
