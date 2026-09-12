---
name: mindshub-orchestrator
description: "Drive the in-house harness: builder and mentor engines, the agent registry, data engine, empirical proof runs, and institutional HTML and PDF tear-sheet generation."
---

# MindsHub Multi-Agent Orchestrator & Reporting

MindsHub is the in-house harness that ties the other five repositories together: a
two-agent loop (mentor designs and audits, builder implements and simulates), a data
engine, an empirical proof script and an institutional HTML report generator.

Code: `quant_bot/` (the harness) and `quant_engine/` (standalone scaffolding helpers).

## The dual-agent loop

```text
1. Episteme (mentor)  -> create_blueprint(goal, ticker)
2. Praxis  (builder)  -> process_task("build_and_optimize", {symbol})
3. Episteme (mentor)  -> audit_backtest(best_metrics)
4. Delivery           -> verdict, signal, parameters, generated LEAN code
```

`QuantMasterBot` in `quant_bot/orchestrator.py` owns both agents and runs
`run_collaborative_pipeline(strategy_goal, ticker)`, returning a dictionary keyed
`collaboration_steps` with the four stages above.

## Command line

```bash
python -m quant_bot.bot agents                       # list the two agents
python -m quant_bot.bot skills                       # list the mapped skills
python -m quant_bot.bot run --ticker SPY --goal "Momentum rotation"
python -m quant_bot.bot audit-file --path path/to/bot.py
```

`audit-file` runs `EpistemeMentorAgent.review_bot_source_code`, a static audit that
starts at 100 and deducts for missing cost modelling, missing signal lag, missing risk
controls and missing validation, returning an institutional score and a verdict of
`APPROVED_FOR_TESTING` (75 or above) or `REJECTED_NEEDS_FIXES`.

## Data provenance is enforced, not assumed

`MarketDataEngine.get_ohlcv` tries `yfinance` and, if that fails, falls back to a
geometric Brownian motion simulator. That fallback is now **explicit**:

- the returned frame carries `df.attrs["synthetic"]` and `df.attrs["source"]`
- a warning is printed naming the failure reason
- `allow_synthetic=False` raises instead of fabricating prices
- the seed is derived with SHA-256, not the process-randomised `hash()`, so the same
  symbol produces the same series across runs

The builder propagates `synthetic_data`, `data_source`, `n_trials` and
`selection_basis` into the metrics dictionary, and the mentor's `audit_backtest`
returns `REJECTED_SYNTHETIC_DATA` when the prices were fabricated. That rejection
outranks every other check, because a Sharpe ratio computed on a random walk is not
a weak result, it is not a result at all.

**Use `allow_synthetic=False` for anything whose numbers you will report.** The
default is permissive so the pipeline can be exercised without network access.

## Known limits of the harness

State these rather than letting a reader assume otherwise.

1. **Selection is in-sample.** `optimize_hyperparameters` sweeps a nine-point grid and
   picks the highest Sharpe over the whole sample. The metrics carry
   `selection_basis: "in_sample_full_period"` and `n_trials`, and the mentor flags it,
   but the harness does not itself do walk-forward selection. For a real study, run
   the ML4T case-study pipeline or the vectorbt walk-forward recipe instead.
2. **The backtest is a single-asset EMA crossover.** `run_vectorized_backtest` is a
   NumPy implementation with fees and slippage and a correctly lagged signal, but it
   is not vectorbt and it is not a portfolio.
3. **The "Qlib alpha factors" are pandas approximations** of three Qlib expressions,
   not a Qlib run. They are labelled as such in the code comments.
4. **The generated LEAN code uses PascalCase.** Current LEAN exposes snake_case to
   Python. Regenerate through `lean-algorithm-builder` before running it.
5. **`quant_engine/builder.py` and `mentor.py`** are standalone scaffolding scripts,
   separate from `quant_bot/`. They emit template strategies rather than running them.

## Reporting

```python
from quant_bot.report_generator import QuantReportGenerator

gen = QuantReportGenerator()                      # defaults to the repository root
html_path = gen.generate_html_summary(result)
json_path = gen.generate_json_summary(result)
```

The report renders a provenance banner when the run used synthetic data, a metrics
table, the mentor's verdict with strengths, critiques and recommendations, the
blueprint, and one panel per stage. It reads `collaboration_steps` and still accepts
the legacy `stages` key.

## The empirical proof script

`python -m quant_bot.empirical_proof` demonstrates two things worth internalising:

1. **Win rate is not edge.** An 80% win rate with a 10 to −55 payoff has expectancy
   `0.8 × 10 + 0.2 × (−55) = −3.0` per trade. A 45% win rate at 25 to −10 has
   expectancy `+5.75`. The first bot looks better on every dashboard and loses money.
2. **Risk management dominates signal quality** over a long enough sequence.

Use it when someone presents a high win rate as evidence.

## References

- Module and class inventory: [api-reference.md](references/api-reference.md)
- Report structure and how to extend it: [reporting.md](references/reporting.md)
- Auto-generated repository map: [project-structure.md](references/project-structure.md)
- Auto-generated dependency map: [tech-stacks.md](references/tech-stacks.md)

## Related skills

`quant-builder` and `quant-mentor` are the agent manuals this harness implements in
code. `backtest-risk-audit` is the full version of what `audit_backtest` approximates.
`repomix-context-packaging` packs this repository for an LLM.
