# ML4T Chapter Map

Twenty-seven chapters in `machine-learning-for-trading/`. Use this to answer "where in
the book" without guessing. Paths are directory names; notebooks inside are Jupytext
`.py` sources.

| # | Directory | What it teaches | Notable files |
|---|---|---|---|
| 1 | `01_process_is_edge` | Process as the durable edge; regimes and drift | `factor_regimes.py`, `macro_regimes.py` |
| 2 | `02_financial_data_universe` | Data taxonomy, point-in-time discipline, storage | `13_data_quality_framework.py`, `14_point_in_time_validation.py`, `15_survivorship_bias_detection.py`, `20`–`22` storage benchmarks |
| 3 | `03_market_microstructure` | Limit-order-book reconstruction from ITCH, Databento MBO, IEX, AlgoSeek TAQ; bar sampling; Lee-Ready; information bars | `limit_orderbook.py`, `itch_message_specs.py` |
| 4 | `04_fundamental_alternative_data` | Bitemporal fundamentals: SEC XBRL, Form 4, 13F, FRED macro, entity resolution, prediction markets | |
| 5 | `05_synthetic_data` | Classical simulation plus TimeGAN, TailGAN, SigCWGAN, GT-GAN, Diffusion-TS, GReaT, DP-GAN | `01_timegan.py` … `07_dp_gan.py` |
| 6 | `06_strategy_definition` | The strategy framework and cross-validation from first principles | `02_cv_foundations.py` |
| 7 | `07_defining_the_learning_task` | Preprocessing, labels, MFE/MAE, signal evaluation, IC inference, multiple testing, causal sanity checks | `05_signal_evaluation.py`, `06_ic_inference.py`, `07_multiple_testing.py`, `10_ml4t_library_ecosystem.py` |
| 8 | `08_financial_features` | Price and volume, microstructure, cross-instrument, fundamental and macro features; selection, robustness, event studies | `01_price_volume_features.py`, `02_microstructure_features.py`, `05_feature_selection.py`, `07_event_studies.py` |
| 9 | `09_model_based_features` | Features that are fitted procedures: breaks, fractional differencing, Kalman, spectral, signatures, ARIMA, GARCH, HAR and rough volatility, HMM and Wasserstein regimes | `03_fractional_differencing.py`, `04_kalman_filter.py`, `06_path_signatures.py`, `08_garch_volatility.py`, `11_hmm_regimes.py` |
| 10 | `10_text_feature_engineering` | Word2Vec, asset embeddings, BERT and FinBERT fine-tuning, NER, news to return signals | `04_bert_finetuning.py`, `06_finbert_cross_dataset.py` |
| 11 | `11_ml_pipeline` | OLS inference, regularisation paths, logistic regression, nested CV and HPO, SHAP, conformal prediction, the ML backtest introduction | `01`–`03` |
| 12 | `12_gradient_boosting` | Random forests and GBM foundations, XGBoost/LightGBM/CatBoost comparison, Optuna tuning, SHAP and the limits of explanation, conformal GBM | `02_gbm_comparison.py`, `04_optuna_tuning.py`, `05_cross_library_hpo.py`, `11_conformal_gbm.py` |
| 13 | `13_dl_time_series` | RNN and LSTM, N-BEATS, Transformers, TCN, TSMixer, Mamba state-space models, CNN image encoding, foundation models | `01_core_architectures.py`, `02_nbeats_interpretable.py`, `04_transformers.py`, `05_tcn.py`, `06_tsmixer.py`, `07_mamba_ssm.py`, `08_cnn_image_encoding.py`, `09_foundation_models.py`, `dl_sequences.py` |
| 14 | `14_latent_factors` | PCA and eigenportfolios, yield curve, IPCA, RP-PCA, conditional autoencoder, stochastic discount factor, supervised autoencoder | `06_conditional_autoencoder.py`, `07_stochastic_discount_factor.py`, `08_supervised_autoencoder.py` |
| 15 | `15_causal_estimation` | DoWhy DAGs, EconML double machine learning, BSTS event studies, Tigramite, neural causal discovery, factor-zoo validation | `03_econml_dml.py` |
| 16 | `16_strategy_simulation` | Backtest protocol, engine parity across vectorbt/Lean/backtrader/zipline, Deflated Sharpe, the RAS protocol, cost sensitivity | `09_performance_reporting.py`, `11_sharpe_ratio_inference.py`, `12_dsr_validation.py` |
| 17 | `17_portfolio_construction` | Mean-variance, robust optimisation, Kelly, hierarchical risk parity, conformal sizing, deep allocation | `01_portfolio_metrics.py`, `02_mean_variance_optimization.py`, `03_robust_optimization.py`, `04_kelly_criterion.py`, `06_hierarchical_risk_parity.py`, `07_conformal_position_sizing.py`, `09_allocator_comparison.py`, `11_dl_portfolio_allocation.py`, `12_vlstm_portfolio.py`, `13_deepm_regime_robust.py` |
| 18 | `18_transaction_costs` | Cost taxonomy, spread estimation, impact calibration, VWAP and TWAP, Almgren-Chriss, the cost cliff | |
| 19 | `19_risk_management` | VaR and CVaR, exits, MAE/MFE sizing, factor exposure, stress tests, drift detection, deep hedging | `01_var_cvar.py`, `03_position_sizing_mae_mfe.py`, `04_factor_exposure.py`, `06_stress_testing.py`, `07_drift_detection.py`, `09_deep_hedging.py`, `11_systematic_risk_sweep.py` |
| 20 | `20_strategy_synthesis` | Cross-case synthesis: feature triage, signal, portfolio, cost survival, regime risk, recommendations | `02_feature_evaluation.py` |
| 21 | `21_rl_execution_hedging` | PPO execution and market making, crypto execution RL, pfhedge deep hedging, inverse RL | `02_optimal_execution_ppo.py`, `03_market_making_ppo.py`, `05_deep_hedging_pfhedge.py`, `06_inverse_reinforcement_learning.py`, `rl_environments.py` |
| 22 | `22_rag_financial_research` | SEC retrieval pipeline, embedding comparison, hybrid retrieval, RAGAS evaluation, RAG security | |
| 23 | `23_knowledge_graphs` | Supply-chain graphs, GraphRAG question answering, 13F graphs, GNN features, temporal graphs, network portfolios | |
| 24 | `24_autonomous_agents` | ReAct, tool contracts, state and memory, multi-agent debate, forecasting pipelines, governance | |
| 25 | `25_live_trading` | Unified backtest/paper/live framework, deployment loops, order state machine, pipeline verification | `01_unified_framework_demo.py`, `02_etfs_deployment_loop.py`, `07_order_state_machine.py`, `08_pipeline_verification.py`, `10_safety_risk_demo.py`, `13_runtime_safety_showcase.py` |
| 26 | `26_mlops_governance` | Drift monitoring, online detection, safe rollout, circuit breakers, Feast, MLflow | `01_drift_monitoring.py`, `02_online_drift_detection.py`, `03_safe_model_rollout.py`, `04_circuit_breakers.py`, `05_feast_feature_store.py`, `06_mlflow_experiments.py` |
| 27 | `27_systematic_edge` | Philosophy, quant careers, the learning arsenal, frontiers, roadmap. README only, no notebooks | |

## Reading routes

**"I want to build a bot."** 6 → 7 → 8 → 11 → 12 → 16 → 17 → 18 → 19 → 25 → 26.

**"My backtest looks too good."** 16 (protocol, Deflated Sharpe) → 7 (multiple
testing) → 2 (survivorship, point in time) → 18 (costs).

**"I need better features."** 8 (observable features) → 9 (fitted-procedure features)
→ 7 (signal evaluation) → 20 (triage).

**"I have a signal, now what?"** 17 (construction) → 18 (costs) → 19 (risk) → 16
(simulation protocol).

**"How do I go live?"** 25 (deployment loop, order state machine, safety) → 26 (drift,
rollout, circuit breakers).

**"Which model family?"** 11 (linear baselines) → 12 (gradient boosting, usually the
answer for tabular cross-sections) → 13 (sequence models, for path-dependent targets)
→ 14 (latent factors, when the cross-section has strong common structure).

## Models by family and where they live

| Family | Chapter notebooks | Case-study stage | Config presets |
|---|---|---|---|
| Linear | `11_ml_pipeline/01`–`03` | `06_linear.py` | `case_studies/config/{ols,ridge,lasso,elastic_net,logistic}/` |
| Gradient boosting | `12_gradient_boosting/02,04,05,11` | `07_gbm.py` | `config/lgb/` |
| Tabular deep learning | — | `08_tabular_dl.py` | `config/tabm/` |
| Sequence models | `13_dl_time_series/01`–`09` | `09_dl_lstm.py`, `10_dl_tsmixer.py`, `10a_dl_nlinear.py` | `config/{lstm,tcn,tsmixer,nlinear,patchtst,nbeats}/` |
| Latent factors | `14_latent_factors/06`–`08` | `11a`–`11e` | `config/{pca,ipca,cae,sae,sdf}/` |
| Causal | `15_causal_estimation/03` | `12_causal_dml.py` | `config/dml/` |
| Generative | `05_synthetic_data/01`–`07` | — | — |
| Reinforcement learning | `21_rl_execution_hedging/02,03,05,06` | — | — |

## Environment

`pyproject.toml` pins Python 3.14 with `uv.lock`. Docker images live in
`envs/ml4t/Dockerfile`, `envs/py312/Dockerfile`, `envs/rapids/Dockerfile`,
`envs/benchmark/`, plus a root `docker-compose.yml`. No conda YAML and no
`requirements.txt`. Documentation: `docs/installation.md`, `docs/running-notebooks.md`,
`docs/what-this-is.md`. Also `.env.example`, `sitecustomize.py`, `matplotlibrc`,
`.pre-commit-config.yaml`, `envs/scan_imports.py`, `scripts/verify_installation.py`.

Environment variables: `ML4T_DATA_PATH`, `ML4T_OUTPUT_DIR`, and in `.env`:
`EDGAR_IDENTITY`, `FRED_API_KEY`, `QUANDL_API_KEY`, `OANDA_API_KEY`,
`DATABENTO_API_KEY`, `ALPACA_*`.

Headless execution: `MPLBACKEND=Agg`, `PLOTLY_RENDERER=json`.

## The repository's own agent assets

`.claude/skills/ml4t/` with references `running.md`, `case-studies.md`, `run-log.md`,
`data-loaders.md`, `notebook-conventions.md`; `.claude/skills/ml4t-quant-bot-mentor/`
with a nine-phase `references/roadmap.md`, `references/bot-template.md` and
`references/mentor-protocol.md`. Agents in `.claude/agents/`: `ml4t-mentor` (read-only)
and `ml4t-bot-builder`. Bots are built as experiments with deployment code under
`bots/<bot_id>/`, following `25_live_trading/02_etfs_deployment_loop.py` and monitored
per `26_mlops_governance/01`–`04`. Offline PDFs sit in `pdf_book/`.

Existing bot scaffolds: `bots/_template`, `bots/_shared`, `exness_btc_8h`,
`exness_fx_d1`, `exness_gold_sess`, `exness_usidx_sess`, `xau_fx_mt5`.
