# Review Protocol

## Phase 1 — Orient, five minutes

Before reading any logic, establish what you are looking at.

```bash
# what kind of project is this
ls -la; cat README.md 2>/dev/null | head -40

# where do results come from
grep -rln "sharpe\|Sharpe\|total_return" --include=*.py --include=*.ipynb .

# where is the entry point
grep -rn "if __name__\|def main\|argparse" --include=*.py . | head

# is there configuration, or are parameters inline
find . -name "*.yaml" -o -name "*.yml" -o -name "*.toml" | head
grep -rn "PARAM_GRID\|param_grid\|for .* in \[.*\]:" --include=*.py . | head
```

Ask three questions and get answers before going further: what is the claim, what data
supports it, and how many configurations were tried.

## Phase 2 — Mechanical scan

These greps find most serious problems faster than reading.

```bash
# forward references
grep -rnE "shift\(-[0-9]+\)|\.shift\(-|Ref\([^,]+, *-" --include=*.py .

# backward fill, which copies future values into the past
grep -rnE "bfill|method=['\"]bfill|\.interpolate\(" --include=*.py .

# scalers fitted on everything
grep -rnE "fit_transform\((X|df|data|features)\)" --include=*.py .

# shuffled cross-validation on a time series
grep -rnE "KFold|train_test_split|shuffle=True|cross_val_score" --include=*.py .

# zero or missing costs
grep -rnE "fees?\s*=\s*0(\.0+)?\b|slippage\s*=\s*0(\.0+)?\b|commission\s*=\s*0" --include=*.py .

# hardcoded universes
grep -rnE "symbols?\s*=\s*\[|tickers?\s*=\s*\[" --include=*.py .

# selection on the reported slice
grep -rnE "idxmax\(\)|argmax\(|\.max\(\).*sharpe|best_" --include=*.py .
```

Each hit is a question, not a verdict. `shift(-21)` in a label file is correct;
the same call in a feature file is a bug.

## Phase 3 — Trace one trade end to end

Pick a single decision and follow it through the code, writing down the timestamp at
each step.

```text
t=2023-06-15 16:00  bar closes
t=?                 feature computed        <- from which bars?
t=?                 prediction made
t=?                 order intended
t=?                 fill priced             <- at which bar, at which price?
t=?                 return attributed       <- over which window?
```

If any arrow points backwards, or if the fill is priced from the same bar that produced
the feature, you have found the finding. This exercise catches timing bugs that survive
every automated check because they are distributed across three files.

## Phase 4 — Counterfactuals

Run these rather than describing them. Each one takes minutes and produces a number.

| Test | What it shows |
|---|---|
| add one bar of lag to every signal | timing dependence; a collapse means lookahead |
| double the cost assumption | cost dependence |
| set costs to zero | how much of the result the costs were already eating |
| refit normalisers on the training window only | leakage through preprocessing |
| replace the signal with random signals of the same trade count | whether there is any edge |
| invert the signal | whether the strategy is direction or volatility |
| remove the best five days | concentration |
| split by regime | whether it is a regime bet |
| shift the sample start by one quarter | sensitivity to an arbitrary choice |

Report the ones that changed the answer. Silence on a test you ran and that passed is
fine; a list of nine tests where eight are noise buries the one that matters.

## Phase 5 — Statistics

```python
report = audit_significance(returns, n_trials=<the real count>, periods_per_year=252)
```

Establish the trial count first, by asking directly: how many configurations were
evaluated, including discarded ones and earlier versions of the idea. If the answer is
"I did not count", the count is unknown and every significance statement is provisional.
Say that plainly.

Then report, in this order: observations, effective observations given label overlap,
trades, observed Sharpe, trials, deflated Sharpe, and the minimum track record length.
That last number frequently ends the discussion on its own.

## Phase 6 — The verdict

```text
VERDICT: not evidence yet

BLOCKING
  1. Preprocessing leak, features.py:88. The 60-day z-score is fitted on the full
     series before the split. Refitting on training data only drops validation
     Sharpe from 1.90 to 0.71.
     Fix: move the fit inside the fold loop, or use RobustZScoreNorm with an
     explicit fit window as in qlib/qlib/data/dataset/processor.py.

MATERIAL
  2. Trial count is unrecorded. At least 48 configurations appear in the notebook
     history. At 48 trials the expected maximum Sharpe under no edge is about 0.62
     period-adjusted, which the corrected result does not clear.
  3. Costs are 1 bp round trip (backtest.py:44) with no stated source. At the
     strategy's 620% annual turnover, 10 bps would remove 6.2% a year.

NOTED
  4. Universe is a hardcoded list of current S&P 100 members (universe.py:12),
     so the result carries survivorship bias of unknown size.

NUMBERS
  Observed Sharpe (as written)     1.90
  Sharpe with leak fixed           0.71
  Sharpe at 10 bps                 0.24
  Trials (minimum)                 48
  Deflated Sharpe                  0.31
  Cost zero-crossing               13 bps

NEXT SINGLE MOST USEFUL STEP
  Fix the normalisation boundary and rerun. Everything else is secondary until
  that number is trustworthy.
```

## Teaching alongside the audit

Attach a short explanation to each blocking finding. The audit stops a bad result; the
explanation stops the next one.

> **Why this matters.** A z-score fitted on the whole sample encodes the test period's
> mean and variance. The model then knows, implicitly, whether the test period was
> calm or volatile relative to the whole history. That is information nobody had at the
> time, and it inflates exactly the periods where a volatility-sensitive strategy makes
> its money.
>
> **Where to read more.** `06_strategy_definition/02_cv_foundations.py` in the ML4T
> repository derives this, and `qlib/qlib/data/dataset/processor.py` shows the fix as a
> library primitive.

## Reviewing a design rather than code

When there is no code yet, the questions change but the order does not.

1. What is the hypothesis, and what would falsify it?
2. What data does it need, and does that data exist point-in-time?
3. What is the label, and does its horizon match the intended holding period?
4. What is the turnover, and what does that cost?
5. Does a naive version survive that cost?
6. What is the split geometry?
7. How many things will be tried, and how will that be counted?
8. What is the holdout, and what will be done if it disagrees with validation?

Question 8 is the one that predicts whether the project will produce trustworthy work.
An answer of "we would investigate why the holdout is wrong" is the wrong answer, and
worth saying so before the work starts rather than after.

## Reviewing someone else's claim about a strategy

For a vendor pitch, a paper or a forum post, the questions are:

- Over what period, and does it include a crisis?
- Net of what costs, and at what size?
- How many strategies were tested to find this one?
- Is the universe survivorship-free?
- Is the track record live or simulated? If both, when did live start?
- What is the capacity, and how was it estimated?
- What is the worst drawdown, and how long did recovery take?

The absence of an answer is itself informative. A Sharpe quoted without a cost
assumption is a marketing number.
