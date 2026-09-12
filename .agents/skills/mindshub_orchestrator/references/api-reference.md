# MindsHub Harness API Reference

## Package layout

```text
quant_bot/
  __init__.py            version marker
  bot.py                 CLI: agents | skills | run | audit-file
  orchestrator.py        QuantMasterBot, the four-stage collaborative loop
  data_engine.py         MarketDataEngine with explicit synthetic fallback
  report_generator.py    QuantReportGenerator, HTML and JSON tear sheets
  empirical_proof.py     expectancy and risk-management demonstrations
  sync_mindshub.py       copies .agents/skills into ~/.anton and ~/.cowork
  agents/
    base_agent.py        BaseQuantAgent (abstract)
    mentor_agent.py      EpistemeMentorAgent
    builder_agent.py     PraxisBuilderAgent
    awesome_quant_agent.py, lean_agent.py, qlib_agent.py, vectorbt_agent.py
quant_engine/
  builder.py             standalone strategy scaffolding
  mentor.py              standalone audit helpers
```

## `BaseQuantAgent` — `quant_bot/agents/base_agent.py`

```python
class BaseQuantAgent(ABC):
    def __init__(self, name, role, primary_skill, system_prompt, framework_path): ...

    @abstractmethod
    def get_capabilities(self) -> List[str]: ...

    @abstractmethod
    def process_task(self, task_type: str, parameters: Dict[str, Any]) -> Dict[str, Any]: ...

    def get_info(self) -> Dict[str, Any]: ...
```

Every agent exposes a name, a role, a primary skill label, a system prompt and a
framework path. `get_info()` is what the CLI prints.

## `EpistemeMentorAgent` — `quant_bot/agents/mentor_agent.py`

`REPO_ROOT` resolves to the repository, and `awesome_quant_path` defaults to
`REPO_ROOT / "awesome-quant"`.

| Method | Returns |
|---|---|
| `create_blueprint(user_goal, target_asset="BTC-USD")` | blueprint dict: paradigm, toolchain, alpha factors, risk limits, builder instructions |
| `audit_backtest(backtest_metrics)` | `audit_verdict`, `institutional_flags`, `recommendation`, `metrics_evaluated` |
| `review_bot_source_code(code_text, filename="bot.py")` | `institutional_score` (0-100), `audit_verdict`, `strengths`, `critiques`, `recommendations` |
| `get_capabilities()`, `process_task(task_type, parameters)` | |

### `audit_backtest` checks, in order

| Check | Trigger | Effect |
|---|---|---|
| 0 provenance | `synthetic_data` is true | `REJECTED_SYNTHETIC_DATA`, overrides everything below |
| 0b selection | `selection_basis == "in_sample_full_period"` | warning naming `n_trials`, downgrades an otherwise-approved verdict |
| 1 Sharpe too high | `sharpe > 3.5` | `NEEDS_REVISION` |
| 1b Sharpe too low | `sharpe < 1.0` | `NEEDS_REVISION` |
| 2 drawdown | `abs(max_drawdown) > 0.20` | `NEEDS_REVISION` |
| 3 sample size | `total_trades < 30` | caution only |
| 4 win rate | `win_rate > 0.85` | `NEEDS_REVISION` |

The blueprint's default risk limits: `max_portfolio_drawdown = 0.08`,
`per_trade_risk = 0.02`, `slippage_model = 0.0005`, `fee_model = 0.001`.

### `review_bot_source_code` deductions

Starts at 100 and subtracts for missing cost modelling (−40), missing signal lag
(−30), missing risk controls (−25) and missing validation (−15). Verdict is
`APPROVED_FOR_TESTING` at 75 or above, otherwise `REJECTED_NEEDS_FIXES`.

## `PraxisBuilderAgent` — `quant_bot/agents/builder_agent.py`

`REPO_ROOT` resolves to the repository; `qlib_path`, `vectorbt_path` and `lean_path`
default to the sibling checkouts.

| Method | Notes |
|---|---|
| `compute_qlib_alpha_factors(df)` | pandas approximations of three Qlib expressions: 5-day momentum, volatility ratio (`Std(5)/Std(20)`), volume surge (`$volume / Mean($volume,20) - 1`), plus a `tanh` composite z-score |
| `run_vectorized_backtest(df, fast_span=12, slow_span=36, fees=0.001, slippage=0.0005)` | EMA crossover with the signal lagged one bar and costs charged on position changes |
| `optimize_hyperparameters(df, fast_grid=[8,12,16], slow_grid=[24,36,48])` | nine-point grid, selects the highest Sharpe **in-sample** |
| `generate_lean_production_code(symbol, fast, slow, max_dd_pct=0.08)` | emits a `QCAlgorithm` template (PascalCase; regenerate for current LEAN) |
| `process_task("build_and_optimize", {"symbol": ...})` | orchestrates the above |

`run_vectorized_backtest` returns `annualized_return`, `total_return`, `sharpe_ratio`,
`sortino_ratio`, `max_drawdown`, `win_rate`, `total_trades`, `fast_span`, `slow_span`,
`current_signal`, `latest_close`.

`process_task` adds `data_source`, `synthetic_data`, `n_trials` and `selection_basis`
to both the top-level result and the `best_backtest` dictionary, so the mentor can
audit how the number was produced rather than only what it is.

**The signal lag is correct.** `positions[1:] = np.where(raw_signal[:-1], 1.0, 0.0)`
acts on the previous bar's crossover, which is the property most home-grown
backtesters get wrong.

## `MarketDataEngine` — `quant_bot/data_engine.py`

```python
get_ohlcv(symbol="BTC-USD", start_date="2023-01-01", end_date="2024-01-01",
          n_days=365, allow_synthetic=True) -> pd.DataFrame
```

Returns a frame with `Open, High, Low, Close, Volume` and the attributes
`synthetic` (bool) and `source` (`"yfinance"` or `"gbm_simulation"`).

Synthetic calibration by symbol: BTC `35000 / 0.0008 / 0.035`,
ETH `2200 / 0.0009 / 0.042`, XAU or GOLD `1950 / 0.0004 / 0.012`,
SPY `450 / 0.0005 / 0.011`, EUR `1.08 / 0.0001 / 0.006`, otherwise
`100 / 0.0004 / 0.020`. Volatility clustering is applied by scaling the return after
any move larger than 1.5 sigma. The seed is
`int(sha256(symbol)[:8], 16) % 1000000`, so runs are reproducible.

## `QuantMasterBot` — `quant_bot/orchestrator.py`

```python
bot = QuantMasterBot()
bot.list_agents()                                   # both agents' get_info()
bot.list_skills()                                   # the four mapped skill labels
result = bot.run_collaborative_pipeline(goal, ticker="BTC-USD")
result = bot.run_pipeline(goal, ticker)             # compatibility alias
```

Result shape:

```python
{
  "timestamp": "...", "pipeline_goal": "...", "ticker": "...", "status": "completed",
  "collaboration_steps": {
    "1_mentor_blueprint":    {"agent", "role", "output"},
    "2_builder_simulation":  {"agent", "role", "output"},
    "3_mentor_audit":        {"agent", "role", "output"},
    "4_production_delivery": {"verdict", "ticker", "current_signal", "sharpe_ratio",
                              "max_drawdown", "total_return", "optimal_parameters",
                              "lean_algorithm"},
  },
}
```

## `QuantReportGenerator` — `quant_bot/report_generator.py`

```python
QuantReportGenerator(workspace_root=None)           # defaults to the repository root
generate_html_summary(pipeline_result, output_path=None) -> str
generate_json_summary(pipeline_result, output_path=None) -> str
```

Reads `collaboration_steps`, falling back to `stages`. Renders a provenance banner
when `synthetic_data` is set, a metrics table driven by `_METRIC_ROWS`, the audit
panel, the blueprint and one panel per stage.

## `sync_mindshub.py`

Copies every skill directory under `.agents/skills` into `~/.anton/skills` and
`~/.cowork/anton/skills`. The source directory is resolved relative to the repository,
and the skill list is discovered rather than hard-coded, so newly built skills sync
without editing the script.

## `quant_engine/`

`builder.py` exposes `scaffold_vectorbt_strategy(target_dir, strategy_name)` and
`scaffold_lean_strategy(target_dir, strategy_name)`, which write template runner
scripts. `mentor.py` provides standalone audit helpers. These are separate from
`quant_bot/` and do not participate in the orchestrated loop.
