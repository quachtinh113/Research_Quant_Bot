---
name: alpha-research-workflow
description: "Take a hypothesis to a validated signal: label design, feature families, purged walk-forward splits, information-coefficient inference, multiple-testing control and signal decay."
---

# Alpha Research Workflow

How a hypothesis becomes a validated signal, tool-agnostic. Qlib, vectorbt and the
ML4T case studies each implement a version of this; the ordering below is what they
have in common and what makes their outputs comparable.

## The sequence

```text
hypothesis -> feasibility -> label -> features -> split -> fit -> IC -> decay -> portfolio
                   |                                              |
                   +-- stop here if the universe cannot pay ------+-- stop here if no IC
```

Two stopping points earn their place. Most abandoned research should have stopped at
one of them, and stopping is a result.

## 1. Write the hypothesis down first

A usable hypothesis names the effect, the mechanism, the horizon and the universe.

> Stocks whose 60-day realised volatility has fallen sharply relative to their
> one-year average outperform over the following month, because volatility
> compression precedes directional resolution and institutional flows chase the
> breakout.

Compare that with "momentum works". The first is falsifiable and tells you what to
measure. The second licenses a thousand configurations, which is exactly how a trial
count gets out of hand.

Record the hypothesis before the first backtest. That record is what distinguishes a
pre-registered test from a search.

## 2. Feasibility before modelling

ML4T's `01_feasibility_analysis` stage exists because the most common research failure
is modelling a universe that cannot support the strategy.

Ask, with numbers:

- What is the median daily dollar volume of the tradable universe?
- At the intended turnover, what fraction of that volume does the strategy take?
- What is the round-trip cost, and what annual return does that imply?
- Does a naive version of the effect survive that cost at all?

If a costless version of the idea earns 3% a year and the cost is 4%, the research is
finished. Say so and move on.

## 3. Label design

The label is the question. Get it wrong and everything downstream answers a different
question.

| Choice | Consequence |
|---|---|
| Horizon | must match the intended holding period and the rebalance cadence |
| Return definition | simple, log, excess over benchmark, or residual after factors |
| Cross-sectional or absolute | ranking needs a cross-sectional label; timing needs an absolute one |
| Classification or regression | classification loses magnitude; regression is noisier but sizes positions |
| Triple barrier | takes stops and targets into account, at the cost of a path-dependent label |

**Overlapping labels are the silent killer.** A 21-day forward return computed daily
gives observations that share 20 of 21 days. The effective sample is roughly `n / 21`,
not `n`, and every t-statistic computed on the naive count is inflated by about 4.6
times. Either sample non-overlapping, or purge the overlap in cross-validation, or
correct the standard errors. Do not do none of the three.

The Qlib default `Ref($close, -2)/Ref($close, -1) - 1` encodes an assumption worth
copying: you decide today, you trade tomorrow, you earn the day after.

## 4. Features in families

Group features by what produces them, not alphabetically. Families let you reason
about redundancy and about what to drop when the signal is weak.

| Family | Examples | Watch for |
|---|---|---|
| Price and volume | returns over horizons, realised volatility, range, relative volume | high mutual correlation; a dozen momentum windows is one feature |
| Microstructure | spread, order imbalance, Kyle's lambda, VPIN | needs tick or quote data; often unavailable at the frequency claimed |
| Cross-sectional | rank, percentile, z-score within the universe | changes meaning when universe composition changes |
| Fundamental | valuation ratios, growth, quality | point-in-time or nothing |
| Macro | rates, curve slope, credit spreads, commodity levels | low frequency; easily overfitted by a daily model |
| Model-based | Kalman states, GARCH volatility, HMM regime, fractional difference, path signatures | the fitting procedure itself must respect the split |

That last row matters most. A GARCH volatility feature fitted on the whole sample and
then used as an input is a leak, even though nothing about it looks like a forward
shift.

Two disciplines for every feature: state its **timing contract** (what is the latest
timestamp it uses) and its **warm-up period** (how many observations before it is
valid). ML4T's `feature_engineering.py` has `warmup_audit` and `plot_timing_contract`
for exactly this.

## 5. Splits before fits

Decide the split geometry before running a model, and derive it from the label
horizon.

```text
|-- train --|purge|-- validation --|embargo|-- ... -- |--- holdout ---|
```

- **Purge** removes training observations whose labels overlap the validation window.
  Length equals the label horizon.
- **Embargo** removes validation observations immediately after training, guarding
  against serial correlation leaking backwards through features.
- **Walk-forward** repeats this, rolling or expanding, so you get several
  out-of-sample estimates rather than one.

Anchor the geometry in configuration, not in a notebook. ML4T does this through
`setup.yaml` and `utils.cv_splits`.

## 6. Fit, but start with a baseline

Fit a linear model first. It is fast, it is interpretable, and it establishes the
number a complex model has to beat. A gradient-boosted tree that improves on ridge
regression by 4% of an information coefficient is not worth the operational cost.

Order: linear, then gradient boosting, then sequence or latent-factor models if the
data has structure they can exploit. Move on only when the simpler model is clearly
beaten on validation, across folds, not on average.

## 7. Information coefficient, read properly

```python
ic = predictions.groupby(level="datetime").corr(labels, method="spearman")
```

Then look at four things, in this order:

1. **Stability across folds.** A model that wins in five folds of eight and loses in
   three has not generalised, whatever the pooled mean says.
2. **Positive rate.** The share of periods with positive IC. Near 0.5 with a decent
   mean means a handful of periods carry everything.
3. **ICIR**, the mean divided by the standard deviation, annualised. Around 0.3 and
   above is worth pursuing for a daily cross-section.
4. **Bucket monotonicity.** Sort predictions into deciles and check that realised
   returns increase across them. A good mean IC with a non-monotone profile usually
   means the model only separates the tails.

Only then look at the mean IC.

## 8. Decay tells you the holding period

Compute IC against forward returns at 1, 2, 3, 5, 10, 21 and 42 days. The shape
answers questions you would otherwise guess at:

- The peak horizon is the natural holding period.
- The decay rate bounds how quickly you must trade, and therefore your cost.
- A signal that peaks at one day and is gone by three is a microstructure effect and
  will not survive retail-level costs.
- A flat profile across all horizons is usually a slow-moving factor exposure rather
  than an alpha.

## 9. Multiple testing, kept honest

Keep a running count of every configuration evaluated: features tried, models, label
variants, universes, cost assumptions, allocators. The count is an input to the
Deflated Sharpe Ratio and to any t-statistic you report.

Practical control:

- Pre-register the primary hypothesis, and label everything else exploratory.
- Apply a Benjamini-Hochberg false-discovery-rate correction across the factors tested.
- Use the ML4T run log, or any content-addressed registry, so the count is a query
  rather than a memory.

The comfortable lie is that discarded variants do not count. They do.

## 10. Handing over to portfolio construction

A validated signal is not a strategy. What passes to the next stage is:

- the prediction series, with its timestamp convention stated
- the label definition and horizon
- the fold geometry and the number of trials
- the validation IC and its stability
- the decay profile
- the universe and its liquidity profile

`portfolio-construction-risk` turns that into weights. `execution-costs-microstructure`
prices the turnover those weights imply. `backtest-risk-audit` decides whether the
whole chain is evidence.

## References

- Detailed procedures and code: [playbook.md](references/playbook.md)

## Related skills

`qlib-alpha-mining` and `vectorbt-backtest` implement steps 4 to 7; `ml-for-trading`
is the full version with a run log; `backtest-risk-audit` is the gate at the end.
