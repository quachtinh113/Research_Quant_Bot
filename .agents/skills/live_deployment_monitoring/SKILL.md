---
name: live-deployment-monitoring
description: "Move from research to production safely: parity checks, the order state machine, paper-trading gates, circuit breakers, drift monitoring and safe model rollout."
---

# Live Deployment & Monitoring

The gap between a validated backtest and a funded account is where most systematic
trading fails, and it fails operationally rather than statistically. This skill is the
path across that gap and the instrumentation that keeps it honest afterwards.

## The gates

Do not skip a gate because the backtest was good. Each one catches a different class
of failure.

```text
holdout passed
   -> 1. parity      : the live code path reproduces the backtest on the same data
   -> 2. replay      : it reproduces the backtest on a live-shaped data feed
   -> 3. paper       : it trades a paper account for a stated period
   -> 4. small live  : real money at a size where being wrong is affordable
   -> 5. scale       : size increases only as realised behaviour matches expectation
```

**Gate 1, parity**, is the one people skip and the one that catches the most. Run the
production code over the backtest period and compare the position series to the
research result, position by position. Any divergence is a bug in one of them, and you
need to know which before real money is involved.

Divergences almost always come from the same short list: a feature computed on a
different window, a timezone difference, a rounding or lot-size rule present in one
path and not the other, a data vendor whose live feed differs from its history file, or
a fill assumption that only exists in the simulator.

**Gate 3, paper trading**, must run long enough to see the strategy's own cycle. A
weekly rebalancer needs months, not days. Decide the duration and the pass criteria
before starting, or the result will be interpreted to fit the desired conclusion.

## The order state machine

Live trading is asynchronous, and every asynchronous system needs an explicit state
machine. Implicit ones fail at 3am.

```text
INTENDED -> SUBMITTED -> ACKNOWLEDGED -> PARTIALLY_FILLED -> FILLED
                |              |                |
                +-> REJECTED   +-> CANCELLED    +-> EXPIRED
```

Rules that prevent the expensive failures:

- Every order carries an idempotency key, so a retry after a timeout cannot double the
  position.
- Reconcile broker positions against internal state on every cycle, and halt on a
  mismatch rather than trading through it.
- Never infer a fill from a timeout. Query the broker.
- Persist state before sending, not after, so a crash mid-send is recoverable.
- Treat an unknown state as a position you might hold, not one you do not.

ML4T's `25_live_trading/07_order_state_machine.py` is the reference implementation, and
`08_pipeline_verification.py` covers gate 1.

## Circuit breakers

Automatic halts, evaluated before every order, with a manual reset. Automatic
re-enabling defeats the purpose.

| Breaker | Trips when | Action |
|---|---|---|
| Daily loss | loss exceeds a stated fraction of equity | flatten, halt for the day |
| Drawdown | peak-to-trough exceeds a limit | reduce size, then halt |
| Position limit | any position exceeds its cap | reject the order |
| Leverage limit | gross exposure exceeds a limit | reject the order |
| Order rate | orders per minute exceeds a threshold | halt; this is the runaway-loop guard |
| Data staleness | the last tick is older than a threshold | halt; do not trade on stale prices |
| Reconciliation | broker and internal positions disagree | halt immediately |
| Model output | predictions fall outside their historical range | halt; the model is extrapolating |

The order-rate breaker is the one that saves accounts. A loop bug that submits
thousands of orders does more damage in a minute than a bad model does in a year.

## Monitoring, in three layers

**System health.** Process uptime, data feed latency and gaps, broker connectivity,
order round-trip time, error rate. Failures here look like trading failures and are
not, so separate them.

**Model health.** Feature distribution drift against the training window, prediction
distribution drift, realised information coefficient over a rolling window, and feature
availability. A feature silently becoming all-NaN is a common and quiet failure.

**Strategy health.** Realised versus expected return and volatility, realised versus
modelled slippage, turnover versus plan, hit rate, and drawdown against its historical
distribution.

The comparison that matters is **realised against expected**, not realised against
zero. A strategy earning 4% when the backtest said 12% is failing even though it is
profitable, and the gap is usually cost or timing rather than decayed alpha.

## Drift detection

Two kinds, and they need different responses.

**Covariate drift**: the inputs have moved. Detect with a population stability index
or a Kolmogorov-Smirnov test per feature against the training distribution. A PSI above
about 0.25 warrants investigation.

**Concept drift**: the relationship between inputs and target has changed. Detect
through a falling rolling information coefficient or rising prediction error. This is
the serious one, and retraining on recent data is only a fix if the new relationship is
stable, which is precisely what has just been called into question.

Online detectors such as ADWIN or DDM flag change points faster than a fixed window.
ML4T's `26_mlops_governance/01_drift_monitoring.py` and `02_online_drift_detection.py`
implement both.

## Retraining

Decide the policy in advance and write it down, because deciding after a drawdown
guarantees a decision made under pressure.

- **Scheduled**: retrain every N periods regardless. Predictable, sometimes wasteful.
- **Triggered**: retrain when drift crosses a threshold. Responsive, but the threshold
  is another parameter you can overfit.
- **Never**: keep the frozen model and retire it when it stops working. Underrated, and
  the only policy with no retraining-related lookahead risk.

Whichever you choose, a retrained model goes through the gates again. It is a new
model, not an update.

## Safe rollout

Never replace a running model in one step. Run the candidate alongside the incumbent,
compare predictions and would-be trades, then shift allocation gradually with a
rollback that can be executed in one command. `26_mlops_governance/03_safe_model_rollout.py`
covers the mechanics.

## What to log

Enough to reconstruct any decision after the fact: timestamp, input snapshot hash,
model version, raw prediction, post-overlay target weight, order intent, broker
response, fill, and the state of every circuit breaker. When something goes wrong at
scale, the question is always "what did the system know and when", and only the log can
answer it.

## References

- Implementations and checklists: [playbook.md](references/playbook.md)

## Related skills

`ml-for-trading` chapters 25 and 26 are the full treatment,
`lean-algorithm-builder` for the backtest-to-live code path,
`backtest-risk-audit` for the gate before any of this begins.
