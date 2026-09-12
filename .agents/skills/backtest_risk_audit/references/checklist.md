# Audit Checklist

Run top to bottom. Record an answer for every line, including "not applicable" with a
reason. An unanswered line is a finding.

## A. Provenance

- [ ] What is the data source, and is it named in the code rather than assumed?
- [ ] Is the data **point-in-time**? For fundamentals, does it use the value known at
      the decision date or the latest restated value?
- [ ] Does the universe include **delisted and merged** names for the whole period?
- [ ] Was the universe constructed from membership **as of each date**, not today's
      index composition?
- [ ] Are corporate actions handled? Splits, dividends, symbol changes, spin-offs.
- [ ] If prices are adjusted, are they adjusted **as of each date** rather than
      back-adjusted with information from later?
- [ ] For futures, how is the roll handled, and is the roll cost charged?
- [ ] Are there gaps, and how are they filled? Forward-filling a price across a halt
      creates trades that could not have happened.
- [ ] Is any of the data synthetic or simulated? If so, stop: this is a plumbing test.

## B. Timing

- [ ] For every feature, what is the latest timestamp of data it uses, and is that
      strictly before the decision timestamp?
- [ ] Are signals lagged relative to the bar they are computed from, or is the fill
      priced at a later bar?
- [ ] Any negative shift, `shift(-n)`, `Ref(x, -n)`, or `.pct_change(n).shift(-n)`
      outside a label definition?
- [ ] Are rolling statistics, normalisers and scalers fitted **only** on data before
      the evaluation window?
- [ ] Do cross-validation folds respect time order, with a purge gap at least as long
      as the label horizon and an embargo after the validation window?
- [ ] For intraday work, is the timestamp the observation time or the availability
      time? Vendors often publish the former.
- [ ] Are earnings, news and macro releases timestamped at release, including the
      time of day?

## C. Costs and execution

- [ ] What commission is charged, in basis points or per share, and where does the
      number come from?
- [ ] What slippage model is used? Constant, spread-based, or volume-share?
- [ ] Is market impact modelled at all for the intended size?
- [ ] At what price does a fill occur? Close, next open, VWAP, mid?
- [ ] Could the fill price fall outside the bar's high-low range?
- [ ] Is there a participation cap, and what fraction of daily volume does the
      strategy take at target size?
- [ ] Are short borrow fees and locate availability modelled?
- [ ] Is financing or margin interest charged on leverage?
- [ ] For crypto, is funding charged on perpetuals?
- [ ] What is annual turnover, and what does the cost assumption imply in annual
      return terms?

## D. Selection

- [ ] How many configurations were evaluated in total, across all versions of the
      idea? Write the number down.
- [ ] On which split were parameters chosen: train, validation, or the same data they
      are reported on?
- [ ] Was the holdout looked at more than once?
- [ ] Were features selected using the full sample?
- [ ] Was the model family, the allocator or the cost assumption also chosen on the
      reported data?
- [ ] Were failed variants discarded silently, and are they in the trial count?

## E. Significance

- [ ] Number of independent observations, and the effective number given
      autocorrelation and overlapping labels.
- [ ] Number of trades. Below 30, no metric is informative.
- [ ] Skew and excess kurtosis of the return series.
- [ ] Deflated Sharpe Ratio given the trial count. Value and the trial count used.
- [ ] Probability of backtest overfitting, if a combinatorial split was run.
- [ ] Comparison against a random-signal benchmark with the same trade count.
- [ ] Comparison against the obvious passive alternative: buy and hold, equal weight,
      the benchmark index.

## F. Fragility

- [ ] Sharpe at 0, 5, 10, 20 and 50 basis points round trip. The zero-crossing cost.
- [ ] Performance by calendar year, and across at least one crisis period.
- [ ] Performance of the parameter neighbourhood, not just the chosen point.
- [ ] Result with the best five days removed, and with the best five trades removed.
- [ ] Result with the signal inverted.
- [ ] Result with a one-bar delay added to every fill.
- [ ] Result on a different but comparable universe or venue.
- [ ] Sensitivity to the start date: does shifting the sample by one quarter change
      the conclusion?

## G. Risk and capacity

- [ ] Maximum drawdown, its dates, and time to recovery.
- [ ] Longest time under water.
- [ ] Gross and net exposure over time, and maximum leverage used.
- [ ] Concentration: largest position, largest sector, largest single-name
      contribution to profit.
- [ ] Factor exposures. Is the "alpha" a market, size, value or momentum loading?
- [ ] Capacity: at what notional does participation exceed the cap, and what does the
      cost model say at that size?
- [ ] Behaviour on the worst historical day for the asset class.

## H. Reproducibility

- [ ] Are random seeds set and recorded?
- [ ] Is the exact configuration that produced the reported result stored?
- [ ] Can the run be reproduced from the repository state alone?
- [ ] Are library versions pinned?
- [ ] Are results content-addressed or otherwise linked to their inputs? The ML4T run
      log does this; use it if the work lives there.

## Verdict template

```text
VERDICT: <evidence | not evidence yet | evidence with stated limits>

BLOCKING
  1. <finding> at <file:line>. Effect: <what it does to the result>.
     Fix: <specific change>.

MATERIAL
  2. ...

NOTED
  3. ...

NUMBERS
  Observed Sharpe        : x.xx
  Trials                 : N
  Deflated Sharpe        : x.xx
  Cost zero-crossing     : xx bps
  Worst-year Sharpe      : x.xx
  Result minus best 5 days: x.xx

NEXT SINGLE MOST USEFUL STEP
  <one action>
```

Order findings by their effect on the conclusion, not by how easy they are to fix. A
blocking finding is one that, if true, makes the reported number meaningless.
