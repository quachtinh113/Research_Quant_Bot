---
name: backtest-risk-audit
description: Audit a strategy against the seven deadly quant sins, compute the Deflated Sharpe Ratio and the probability of backtest overfitting, and decide whether a result survives its own trial count.
---

# Backtest & Statistical Risk Audit

This is the skill that decides whether a result is evidence. Everything else in the
suite produces numbers; this decides which of them mean anything.

Start from a stance: **a backtest is a claim, not a measurement.** The claim is that a
strategy would have produced these returns. The audit's job is to find the cheapest
explanation that is not skill.

## The order of operations

Work top down. A failure at step 1 makes steps 2 to 5 irrelevant, so do not compute a
Deflated Sharpe Ratio for a strategy that trades on tomorrow's close.

1. **Provenance** — is the data real, point-in-time and survivorship-free?
2. **Timing** — could every trade have been placed with information available then?
3. **Costs** — are fees, slippage and impact modelled at plausible levels?
4. **Selection** — how many configurations were tried, and on which split?
5. **Significance** — does the result survive its own trial count?
6. **Fragility** — does it survive small perturbations and regime splits?

## The seven deadly quant sins

| # | Sin | How to detect it |
|---|---|---|
| 1 | **Lookahead bias** | any feature using data timestamped at or after the decision; a negative shift; a rolling statistic computed on the full series before splitting; normalisation fitted on all data |
| 2 | **Survivorship bias** | a universe built from today's index members; no delisted names; returns that stop rather than go to zero |
| 3 | **In-sample overfitting** | parameters chosen on the same data they are scored on; a Sharpe that collapses out of sample; a jagged parameter surface |
| 4 | **Data leakage** | a target derived from a feature; an identifier that encodes the answer; cross-validation folds that share overlapping labels |
| 5 | **Unrealistic costs** | zero or token fees; no slippage; fills at the mid or at prices better than the bar's range; unlimited size |
| 6 | **Regime blindness** | one contiguous sample; no crisis period; performance concentrated in a single year |
| 7 | **Short-sale and borrow fantasy** | shorting names with no locate; no borrow fee; no uptick or halt handling; leverage the account could not obtain |

An eighth, increasingly common: **multiple-testing amnesia**, running hundreds of
configurations and reporting only the winner without saying how many were tried.

## Deflated Sharpe Ratio

The Sharpe ratio of the best of N trials is upward-biased even when no strategy has
any edge. The Deflated Sharpe Ratio corrects for that.

```python
import numpy as np
from scipy.stats import norm


def expected_max_sharpe(n_trials: int, var_sharpe: float = 1.0) -> float:
    """Expected maximum Sharpe from n_trials independent, zero-edge strategies."""
    if n_trials < 2:
        return 0.0
    e, sd = np.euler_gamma, np.sqrt(var_sharpe)
    return sd * ((1 - e) * norm.ppf(1 - 1.0 / n_trials)
                 + e * norm.ppf(1 - 1.0 / (n_trials * np.e)))


def deflated_sharpe_ratio(sharpe, n_obs, skew, kurtosis, n_trials, var_sharpe=1.0):
    """Probability the observed Sharpe exceeds what the best of n_trials would give."""
    sr0 = expected_max_sharpe(n_trials, var_sharpe)
    denom = np.sqrt(1 - skew * sharpe + (kurtosis - 1) / 4 * sharpe ** 2)
    return float(norm.cdf((sharpe - sr0) * np.sqrt(n_obs - 1) / denom))
```

Reading it: the output is a probability. Below 0.95 the result is not significant at
the conventional level. A strategy with Sharpe 1.4 from 200 trials over three years of
daily data usually fails; the same Sharpe from a single pre-registered configuration
over ten years usually passes.

Two inputs people get wrong. `n_trials` is **every configuration you ever evaluated**,
including the ones you discarded early and the ones from last month's version of the
idea. And negative skew with fat tails, which is what most short-volatility strategies
have, inflates the denominator and lowers the deflated value, correctly.

vectorbt implements this as `returns.vbt.returns.deflated_sharpe_ratio(trials=n)`.

## Probability of backtest overfitting

The Deflated Sharpe asks whether one number survives. PBO asks whether the **selection
procedure** works at all. Split the sample into S even blocks, form every combination
of S/2 blocks as in-sample and the complement as out-of-sample, pick the best
configuration in-sample and record its out-of-sample rank.

PBO is the fraction of splits where the in-sample winner lands in the bottom half out
of sample. Above roughly 0.5 the selection is worse than random and the process, not
just the result, is broken.

`purgedcv`, `factor-qc` and `Perception-XAlpha Lite` in the awesome-quant index
implement combinatorially symmetric cross-validation directly.

## Fragility checks that take minutes

These catch more real problems than any single statistic.

**Random benchmark.** Generate strategies with the same trade count and holding
period but random entries. If the observed Sharpe sits inside that distribution, there
is no edge. `vbt.Portfolio.from_random_signals` does this in one call.

**Cost sensitivity.** Recompute Sharpe at 0, 5, 10, 20 and 50 basis points round trip.
Report the cost at which it crosses zero. A strategy that dies at 10 basis points is
not deployable at any size.

**Parameter neighbourhood.** Compare the chosen parameters to their neighbours. A
peak that is 40% better than everything adjacent is a fitting artefact; a broad plateau
is a signal.

**Drop the best periods.** Remove the best five days, then the best five trades. If
the result turns negative, the strategy is a small number of events and its confidence
interval is far wider than the Sharpe suggests.

**Split by regime.** Pre-2008, 2008-2009, 2010-2019, 2020, 2022. Report each. A
strategy that only works in one regime is a regime bet, which is fine if stated and
fatal if not.

**Reverse the sign.** If inverting the signal produces a similarly good result, you
have found volatility, not direction.

## Reading the numbers

| Signal | Usual meaning |
|---|---|
| Sharpe above 3 on daily data | a bug, until proven otherwise |
| Win rate above 80% | asymmetric payoff, martingale, or a leak |
| Equity curve with no drawdown | lookahead |
| Sharpe unchanged when costs double | costs are not actually applied |
| Fewer than 30 trades | no statistical content regardless of the metrics |
| Turnover above 100% a month with a 20 bps cost | the cost is the strategy |
| Out-of-sample Sharpe close to in-sample | check that the split is real before celebrating |

## Delivering the verdict

State the verdict, the evidence, and the single change that would most improve
confidence. Be specific about locations.

> **Verdict: not evidence yet.** The z-score feature at `features.py:88` is computed
> with `rolling(60).mean()` over the whole series before the train/test split, so the
> test-period normalisation uses test-period data. Sharpe falls from 1.9 to 0.7 when
> the statistic is fitted on the training window only. Fix that first; the cost and
> significance questions are secondary until it is corrected.

Do not soften a finding into a suggestion. Do not list eleven minor issues and bury
the one that invalidates the result. And when a strategy passes, say so plainly with
the caveats attached, because an auditor who never approves anything is as useless as
one who approves everything.

## References

- Detailed procedures with code: [playbook.md](references/playbook.md)
- The checklist to run against any result: [checklist.md](references/checklist.md)

## Related skills

`alpha-research-workflow` for the process that avoids these problems in the first
place, `execution-costs-microstructure` for calibrating the cost assumption,
`ml-for-trading` for the evidence boundary this skill enforces.
