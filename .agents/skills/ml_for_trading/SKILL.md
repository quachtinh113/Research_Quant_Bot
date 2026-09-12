---
name: ml-for-trading
description: "Apply the Machine Learning for Trading workflow: chapter map, the nine case studies, setup.yaml as single source of truth, purged walk-forward CV, the content-addressed run log, and the holdout discipline."
---

# ML4T Methodology & Case-Study Pipeline

The Machine Learning for Trading repository is the **methodology spine** of this
suite. Qlib mines factors, vectorbt sweeps parameters and LEAN executes, but ML4T
decides what counts as evidence. When those repositories disagree with ML4T on
process, ML4T wins.

Repository: `machine-learning-for-trading/` (a customised third-edition build,
package `ml4t` 3.0.0, `requires-python >= 3.14, < 3.15`, managed with `uv`,
Polars-first, notebooks paired through Jupytext).

## The nine non-negotiable rules

These are the repository's own rules, from its `AGENTS.md` and `CLAUDE.md`. Follow
them exactly; they are not stylistic preferences.

1. **Always run from the repository root.** `uv run python <path>.py`. Running from a
   subdirectory breaks imports and relative data paths. Inside Docker, `python <path>.py`.
2. **Edit the Jupytext `.py` source, never the `.ipynb`.** Regenerate with
   `uv run python scripts/sync_notebooks.py <notebook_path.py>`. `--check` detects
   drift; `--safe-only` syncs documentation-only updates while preserving outputs.
3. **Never modify a baseline `run_log/`.** Published results in
   `case_studies/<cs>/run_log/` are read-only. Create a writable experiment with
   `uv run python scripts/create_experiment.py --cs <case_study> --output <dir>` and
   set `ML4T_OUTPUT_DIR=<dir>`.
4. **Hyper-parameters live in YAML**, either
   `case_studies/<cs>/config/training/<label>.yaml` (menus) or
   `case_studies/config/<model_type>/<name>.yaml` (presets). Never hardcode a
   `PARAM_GRID` in a notebook.
5. **Preserve pinned declarations.** Do not touch `setup.yaml` keys
   `labels.rebalance_step`, `labels.classification_eval_label`,
   `universe.cost_feasible`, `backtest.sweep.htm_cost_cascade.liquid_quantile`, or
   `config/backtest/base.yaml`, without starting from a clean run log.
6. **Selection happens on validation.** Backtest selection must occur on the
   validation split, never on the information coefficient and never on the holdout.
7. **Point-in-time enforcement.** Walk-forward splits come from `setup.yaml` through
   `utils.cv_splits`; purging and embargoing use label buffers.
8. **OpenMP import order.** Import `lightgbm`, `xgboost` or `catboost` **before**
   `scikit-learn`.
9. **No code branching for tests.** Never write `if TEST:`. Reduce a run through
   Papermill parameters (`# %% tags=["parameters"]`) or `execution_tier="preview"`.

## The evidence boundary

This is the idea the whole repository is built around, and it is the one thing to
carry into every other tool in this suite.

```text
train  ->  validation  ->  holdout
 fit       select          touch once, at the end
```

- **Train** fits parameters.
- **Validation** selects everything: model family, hyper-parameters, features, the
  backtest configuration, the allocator, the cost assumption.
- **Holdout** is looked at once, after every choice is frozen, and it is reported
  whatever it says.

The moment you compare two configurations on the holdout, it becomes a validation set
and you no longer have out-of-sample evidence. `18_holdout_predictions.py` and
`19_holdout_backtest.py` exist precisely so the holdout is crossed exactly once.

## Where the pipeline lives

Nine case studies under `case_studies/`: `etfs`, `crypto_perps_funding`,
`nasdaq100_microstructure`, `sp500_equity_option_analytics`, `us_firm_characteristics`,
`fx_pairs`, `cme_futures`, `sp500_options`, `us_equities_panel`.

Each has the same shape:

```text
case_studies/<cs>/
  config/setup.yaml            single source of truth: universe, cadence, execution,
                               costs, labels, walk-forward geometry, sweep grids
  config/training/<label>.yaml  model menus keyed by family
  config/backtest/ config/exploration/
  labels/ features/ evaluation/  generated artefacts
  benchmark/                     tracked references
  run_log/registry.db            content-addressed results
  run_log/{training,predictions,backtest}/<hash>/
```

And the same numbered stages, run in order from the repository root:

```text
01_feasibility_analysis   02_labels                 03_financial_features
04_model_based_features   05_evaluation             06_linear
07_gbm                    08_tabular_dl             09_dl_lstm
10_dl_tsmixer             10a_dl_nlinear            11a_pca … 11e_supervised_autoencoder
12_causal_dml             13_model_analysis         14_backtest
15_portfolio_management   16_risk_management        17_costs
18_holdout_predictions    19_holdout_backtest       20_strategy_analysis
```

Stage 01 is not ceremonial. `01_feasibility_analysis` asks whether the universe can
carry the intended strategy after costs at all. A universe that fails feasibility does
not get a model.

## The run log

Results are content-addressed: the identity is `SHA-256(canonical_json(identity))[:12]`.
Three levels, `training_runs → prediction_sets → backtest_runs`, plus
`prediction_metrics`, `fold_metrics`, `backtest_metrics`, `backtest_fold_metrics` and
`causal_runs` — eight tables, schema in `case_studies/RUN_LOG.md`.

```python
from case_studies.utils.registry import (
    load_training_runs, load_prediction_sets, load_prediction_metrics,
    load_backtest_runs, load_backtest_metrics, read_training_spec,
    read_predictions, resolve_best_predictions, resolve_best_backtest_runs,
)
```

Writers: `register_training_run`, `register_prediction_set`,
`register_prediction_metrics`, `register_backtest_run`, `skip_training_if_complete`.
Higher-level helpers in `case_studies/utils/analytics.py`: `load_model_ic`,
`load_best_ic_per_family`, `load_chapter_backtests`, `load_triage_ledger`,
`registry_path`.

The registry is also the **trial counter**. Every row in `backtest_runs` is a
configuration you tested. That count is exactly what the Deflated Sharpe Ratio needs,
so a strategy's honest significance is computable from the run log itself.

## Shared libraries worth knowing

`utils/`:
- `cv_splits.py` — `generate_cv_splits`, `load_evaluation_config`,
  `make_walk_forward_config`, `normalize_label_buffer`, `most_recent_split`,
  `_purge_holdout_touching_validation`
- `modeling.py` — `ModelingDataset`, `WalkForwardConfig`, `load_modeling_dataset`,
  `get_cv_config`, `load_protocol`, `load_configs`, `seed_everything`,
  `verify_artifact_sidecars`, `validate_temporal_fold_coverage`, `conformal_quantile`
- `paths.py`, `artifact_specs.py`, `data_quality.py`, `style.py`,
  `predictions_cache.py`, `reproducibility.py`, `downloading.py`

`case_studies/utils/` (about fifty modules): `allocation.py`, `backtest_runner.py`,
`backtest_presets.py`, `backtest_loaders.py`, `signals.py`, `folds.py`, `cv_window.py`,
`feature_engineering.py`, `gbm.py`, `linear.py`, `tabular_dl.py`, `deep_learning.py`,
`latent_factors/`, `causal.py`, `conformal.py`, `model_analysis.py`, `analytics.py`,
`strategy_analysis.py`, `registry/`.

`case_studies/research/` is the writing API: `open_study`, `load_model_configs`,
`model_requests`, `resolved_model_plan`, `run_model_population`, with types `Study`,
`ModelRequest`, `ModelPlan`, `ExecutionTier`, `BacktestPlan`.

`data/` is the loader façade: `load_etfs`, `load_us_equities`, `load_sp500_daily_bars`,
`load_sp500_options`, `load_crypto_perps`, `load_cme_futures`, `load_fx_pairs`,
`load_macro`, `load_ff_factors`, `load_firm_characteristics`, `load_nasdaq_itch`,
`load_sec_xbrl_fundamentals`, plus `list_*` helpers and the exceptions
`DataNotFoundError` and `MissingDependencyError`.

External pinned packages: `ml4t-data`, `ml4t-diagnostic` (supplies `WalkForwardCV` and
`cross_sectional_ic_series`), `ml4t-engineer`, `ml4t-backtest`, `ml4t-live`, `ml4t-models`.

## Notable divergences from common practice

- **TA-Lib and Alphalens are not used.** The repository builds its own Polars feature
  blocks through `ml4t-engineer` and `case_studies/utils/feature_engineering.py`. Do
  not add those dependencies to fit a habit.
- **Polars, not pandas, is the default frame.**
- **Python 3.14** with a `uv.lock`. Twelve locked packages have no 3.14 wheels
  (`scikit-learn`, `shap`, `hmmlearn`, `ruptures`, `econml`, `causalml` among them),
  so a local install needs a C/C++ compiler and Python headers. The Docker images in
  `envs/` are the supported path.

## References

- The 27 chapters and what each one teaches: [chapter-map.md](references/chapter-map.md)
- Running the pipeline, splits, run log, gates: [pipeline.md](references/pipeline.md)
- Auto-generated repository map: [project-structure.md](references/project-structure.md)
- Auto-generated dependency map: [tech-stacks.md](references/tech-stacks.md)

## Related skills

`alpha-research-workflow` and `backtest-risk-audit` are the distilled, tool-agnostic
form of this methodology. `quant-data-pipeline` covers chapters 2 to 4,
`portfolio-construction-risk` covers 17 and 19, `execution-costs-microstructure`
covers 18, and `live-deployment-monitoring` covers 25 and 26.
