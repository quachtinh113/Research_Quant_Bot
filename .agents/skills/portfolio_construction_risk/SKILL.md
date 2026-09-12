---
name: portfolio-construction-risk
description: "Turn a signal into positions: mean-variance and robust optimisation, hierarchical risk parity, Kelly sizing, volatility targeting, exposure limits, drawdown control and stress testing."
---

# Portfolio Construction & Risk Overlays

A signal is a prediction. A portfolio is a set of positions with a risk budget. This
skill is the translation, and it is where more value is gained or lost than in the
model that produced the signal.

## The pipeline

```text
signal -> expected returns -> weights -> constraints -> risk overlay -> orders
```

Each arrow is a decision that must be made on validation data like any other, and
counted as a trial like any other.

## Choosing an allocator

| Allocator | Uses | Strength | Weakness |
|---|---|---|---|
| Equal weight | nothing | impossible to overfit, hard to beat | ignores risk differences entirely |
| Inverse volatility | volatilities | cheap risk balancing | ignores correlation |
| Risk parity | covariance | equal risk contribution | needs a stable covariance estimate |
| Hierarchical risk parity | covariance, hierarchy | no matrix inversion, robust to estimation error | not optimal under any single objective |
| Mean-variance | expected returns, covariance | optimal if inputs are right | inputs are never right; extreme weights |
| Black-Litterman | market prior plus views | shrinks toward equilibrium | needs a defensible prior |
| Kelly | expected returns, covariance | maximises long-run growth | brutal drawdowns at full size |

The default recommendation for a signal-driven cross-section is **hierarchical risk
parity or inverse volatility with a signal tilt**, not mean-variance. Mean-variance
maximises the estimation error in its inputs: a covariance matrix estimated from 252
observations across 100 assets is dominated by noise, and the optimiser will happily
put 40% into the asset whose correlation was mis-estimated most.

If you do use mean-variance, shrink the covariance (Ledoit-Wolf), constrain the
weights, and compare against equal weight before believing the improvement.

## Sizing from a signal

Two common approaches, and they answer different questions.

**Cross-sectional ranking.** Convert predictions to ranks, go long the top decile and
short the bottom, weight within the decile by inverse volatility. This is the standard
for a ranking model and it neutralises the level of the prediction, which is usually
poorly calibrated.

**Direct proportional.** Weight by the prediction itself, scaled to a target
volatility. This uses the magnitude, so it requires the model to be calibrated, which
you should check with a bucket-monotonicity test before relying on it.

In both cases, cap individual weights. An uncapped optimiser will concentrate, and
concentration is where the tail risk lives.

## Volatility targeting

```python
scale = target_vol / max(realised_vol_estimate, floor)
weights = raw_weights * min(scale, max_leverage)
```

Volatility targeting is the highest-value single overlay in most systematic
strategies. It reduces drawdowns, improves Sharpe modestly and, more importantly,
makes the strategy's risk stationary so position sizes mean the same thing in 2017 and
2020.

Two details that matter: use a forecast, not a trailing realised number, because
trailing volatility is a lagging indicator that de-levers after the loss; and put a
floor under the estimate, or the scale explodes in quiet markets and you take on ten
times the intended risk just before a shock.

## Kelly, and why to use a fraction of it

Full Kelly maximises long-run growth and produces drawdowns that no allocator survives
in practice. The expected maximum drawdown at full Kelly approaches 50% and stays
there. Use a quarter to a half.

```python
f_star = mu / sigma ** 2                # single asset, continuous approximation
f_used = 0.25 * f_star
```

The estimation problem compounds: `mu` is the hardest quantity in finance to estimate,
and Kelly is linear in it. A 50% error in `mu` is a 50% error in position size.

## Risk overlays

Layer these on top of the allocator, not inside it.

| Overlay | What it does | Typical setting |
|---|---|---|
| Position cap | limits single-name concentration | 5-10% of gross |
| Sector or factor cap | limits unintended common exposure | 20-25% per sector |
| Gross and net limits | bounds leverage and directionality | gross 100-200%, net ±20% for a neutral book |
| Volatility target | stationary risk | 10-15% annualised |
| Drawdown control | de-risks after losses | halve exposure at −10%, flat at −20% |
| Stop loss | bounds a single position | per-instrument, based on MAE analysis |
| Liquidity cap | bounds participation | max 5% of median daily volume |

Drawdown control deserves a warning. A de-risking rule mechanically reduces exposure
after losses, which improves the drawdown statistic and often reduces long-run return,
because it sells at the bottom. Backtest it explicitly rather than adding it as an
obviously-good idea.

## Measuring risk

**Value at Risk** at 95% or 99%: historical, parametric or Monte Carlo. It answers
"how bad is a normal bad day" and says nothing about the tail beyond it.

**Conditional VaR**, the expected loss given a VaR breach, is the more useful number
and the one to optimise against if you optimise against either.

**Factor exposure.** Regress strategy returns on market, size, value, momentum and
quality. A market-neutral strategy with a 0.6 market beta is a levered long. This is
the check that most often reclassifies "alpha" as a factor loading.

**Stress tests.** Replay the worst historical episodes for the asset class and apply
a correlation shock, because correlations converge toward one exactly when
diversification is needed.

## Turnover is a portfolio decision

The allocator determines turnover, and turnover determines cost. A daily-rebalanced
optimiser chasing a signal with a 21-day decay generates twenty times the necessary
turnover.

Controls: rebalance on a schedule rather than on every signal update, apply a no-trade
band so small weight changes are ignored, and penalise turnover directly in the
objective. Then check the cost sensitivity curve, because the right rebalance frequency
is an empirical question answered on validation data.

## References

- Implementations and code: [playbook.md](references/playbook.md)

## Related skills

`execution-costs-microstructure` prices the turnover this skill creates,
`backtest-risk-audit` checks whether the improvement is real, `ml-for-trading` chapter
17 and `case_studies/utils/allocation.py` hold the reference implementations.
