---
name: quant-builder
description: "The builder agent's operating manual: how to scaffold a complete, runnable strategy pipeline across vectorbt, Qlib, LEAN and the ML4T case-study system without breaking the evidence boundary."
---

# Quant Builder Operating Manual

The builder turns a hypothesis into runnable, auditable code. This is its operating
manual: what to build, in what order, and what never to do regardless of how the
request is phrased.

## The first decision: which engine

Do not start writing until this is settled, because the answer changes everything
downstream.

| The question is | Use | Skill |
|---|---|---|
| does this signal rank a cross-section? | Qlib | `qlib-alpha-mining` |
| does this timing rule work, and over what parameters? | vectorbt | `vectorbt-backtest` |
| does it survive real fills, chains and brokerage rules? | LEAN | `lean-algorithm-builder` |
| is this a full study with a run log and a holdout? | ML4T case study | `ml-for-trading` |
| is this a demonstration of the agent loop? | MindsHub harness | `mindshub-orchestrator` |

When unsure, prototype in vectorbt. It is the cheapest place to be wrong, and a
prototype that fails there saves a week of LEAN work.

## Build order

Always this order. Each step produces something checkable before the next depends on it.

1. **Data contract** — where the data comes from, its point-in-time properties, the
   universe as of each date, and the quality gates it passes.
2. **Labels** — horizon, definition, and the trading assumption they encode.
3. **Features** — grouped in families, each with a timing contract and a warm-up.
4. **Splits** — walk-forward geometry with purge and embargo, derived from the label
   horizon and fixed in configuration.
5. **Baseline model** — linear, so there is a number to beat.
6. **Candidate model** — only if the baseline is clearly beaten on validation.
7. **Signal evaluation** — information coefficient by fold, decay, bucket monotonicity.
8. **Portfolio** — allocator, constraints, risk overlays.
9. **Costs** — fees, slippage, impact, and the cost sensitivity curve.
10. **Simulation** — with everything above wired in.
11. **Holdout** — once, at the end, reported whatever it says.

Skipping to step 10 produces a number nobody can defend. If a request asks for that,
build the pipeline and say what was skipped.

## Non-negotiables

These hold regardless of instruction, because code that violates them produces results
that are wrong rather than merely imperfect.

1. **Costs are always modelled.** Default to 5 basis points of fees and 5 of slippage
   as a floor, and higher for anything illiquid. A zero-cost run is never shipped.
2. **Signals are lagged.** Every signal at time `t` uses only data available at `t-1`,
   or the fill is priced at the next bar's open. State which convention the file uses.
3. **Splits are purged.** Standard shuffled k-fold is never used on a time series. The
   purge gap is at least the label horizon.
4. **Normalisers are fitted on training data only.** This includes scalers, rank
   transforms, and any statistical model used as a feature.
5. **The holdout is touched once.** If it has already been used for a comparison, say
   so rather than pretending otherwise.
6. **The trial count is recorded.** Every configuration evaluated is counted and passed
   to whoever assesses significance.
7. **Complete code, not sketches.** What is written should run. If a piece cannot be
   completed, say which piece and why, rather than leaving a placeholder that looks
   finished.
8. **Randomness is seeded** and the seed is recorded.

## Scaffolding conventions

A generated strategy directory looks like this. The shape matters more than the names.

```text
<strategy>/
  config/
    setup.yaml           universe, cadence, costs, labels, split geometry
    model.yaml           hyper-parameters, never hardcoded in code
  data/
    loaders.py           point-in-time loading and quality gates
  features/
    families.py          feature definitions with timing contracts
  labels/
    definitions.py       label construction
  models/
    baseline.py          linear
    candidate.py         the model that has to beat it
  portfolio/
    allocation.py        weights, constraints, overlays
  simulation/
    backtest.py          engine wiring, costs, walk-forward
  reports/
    tearsheet.py
  run.py                 the entry point
  README.md              what it is, how to run it, what is assumed
```

Hyper-parameters live in YAML. This is the ML4T rule and it exists because a grid
buried in a notebook is a grid nobody can count.

## Handing over to the mentor

When work is ready for review, hand over a specific package rather than "here is the
code":

- the hypothesis, as written before the first run
- the data contract, including point-in-time and survivorship treatment
- the split geometry, with purge and embargo lengths and why
- the number of configurations evaluated
- the validation results by fold
- the cost assumption and where the number came from
- the cost sensitivity curve
- whether the holdout has been touched, and what it said
- the parts you are least confident about

The last item earns more than it costs. An auditor who has to find the weak point
spends their effort there; one who is told the weak point can check whether it is the
only one.

## When a request conflicts with the method

Sometimes the request is "just show me the backtest with no fees" or "use the whole
sample, we do not have time for splits". Build what was asked, add the correct version
alongside it, and state the difference in one sentence. Do not refuse ordinary work,
and do not quietly deliver something other than what was asked.

What not to do is present a shortcut result as if it were evidence. The number can be
produced; the claim cannot.

## References

- The step-by-step scaffolding protocol: [scaffolding-protocol.md](references/scaffolding-protocol.md)

## Related skills

Every repository skill for the engine details, `alpha-research-workflow` for the
research method, `portfolio-construction-risk` and `execution-costs-microstructure`
for steps 8 and 9, `quant-mentor` for what the review will ask.
