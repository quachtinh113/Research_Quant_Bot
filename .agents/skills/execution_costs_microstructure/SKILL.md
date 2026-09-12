---
name: execution-costs-microstructure
description: "Model what trading actually costs: spread estimation, market impact calibration, participation limits, VWAP and Almgren-Chriss schedules, and the cost cliff that kills most paper alpha."
---

# Execution, Costs & Microstructure

Costs decide which strategies exist. A signal with a genuine 8% gross return and 9%
implementation cost is not a weak strategy, it is not a strategy. This skill is about
getting the cost number right before it decides for you.

## The cost stack

| Component | Typical size | Scales with |
|---|---|---|
| Commission | 0.1-1 bp institutional equities, 5-10 bps retail crypto | notional or shares |
| Spread | half the quoted spread for a marketable order | liquidity, volatility, time of day |
| Market impact | 5-50 bps depending on participation | the square root of participation |
| Delay cost | signal decay between decision and fill | latency and decay rate |
| Opportunity cost | unfilled or partially filled orders | order aggressiveness |
| Borrow | 25 bps to several percent annually for shorts | availability |
| Financing | the funding rate on leverage or perpetuals | leverage and tenor |

Retail equity backtests usually model the first two and ignore the rest. The rest is
where the money goes at any size worth trading.

## Estimating the spread

If you have quotes, use them. If you only have OHLC bars, the Corwin-Schultz estimator
recovers a usable spread from consecutive high-low ranges, and the Abdi-Ranaldo
estimator improves on it in low-liquidity names.

Reality check: whatever your estimator returns, compare it against a venue's published
statistics for a few names. An estimator producing 2 basis points for a small-cap
stock is broken.

## Market impact

The standard model is a square-root law:

```text
impact_bps = Y * sigma_daily_bps * sqrt(Q / ADV)
```

where `Q` is the order quantity, `ADV` is average daily volume and `Y` is roughly 0.5
to 1.0 for equities. It says impact grows sublinearly, so doubling size costs about
1.4 times more, not twice.

Two consequences worth internalising. **Capacity is not a cliff, it is a slope**: the
strategy degrades continuously as size grows, and the useful question is the notional
at which expected alpha equals expected impact. And **splitting an order across days
reduces impact but increases delay cost**, so the optimal schedule depends on the
signal's decay rate.

## Execution schedules

| Schedule | Trades | Use when |
|---|---|---|
| Market on open or close | one auction | small size, need the reference price |
| TWAP | evenly over time | no volume forecast, low urgency |
| VWAP | proportional to forecast volume | benchmarked against VWAP |
| Percentage of volume | fixed participation rate | size is large relative to ADV |
| Implementation shortfall | front-loaded | the signal decays quickly |
| Almgren-Chriss | optimal under a risk-aversion parameter | you can estimate impact and volatility |

Almgren-Chriss makes the trade-off explicit: executing quickly costs impact, executing
slowly costs volatility risk. The optimal trajectory depends on your risk aversion, and
the answer is usually more front-loaded than intuition suggests when the signal decays.

## The cost cliff

Plot Sharpe against the assumed cost, from zero to about three times your estimate.
Nearly every strategy has a cost at which its Sharpe crosses zero. That number, not the
headline Sharpe, is what tells you whether the strategy is deployable.

- Crossing above 50 basis points: robust to cost, worth pursuing.
- Crossing between 15 and 50: viable at institutional execution, marginal at retail.
- Crossing below 10: not a strategy, whatever the backtest said.

Report the crossing point next to every headline result.

## Microstructure signals

If you have quote or order-book data, these are the standard features. All of them
decay in minutes to hours, so they belong to intraday strategies and cannot rescue a
daily one.

- **Order flow imbalance**: signed volume at the touch, the most reliable short-horizon
  predictor of price.
- **Queue position**: where your passive order sits, which determines fill probability
  more than price does.
- **Kyle's lambda**: price impact per unit of signed flow, a direct liquidity measure.
- **VPIN**: volume-synchronised probability of informed trading, a toxicity proxy.
- **Realised spread and price impact**: decomposes the effective spread into the
  market maker's revenue and the informed-trading cost.

Without quotes you can sign trades with the tick rule, but every one of these features
degrades substantially compared with quote-based signing.

## Modelling costs in each engine

**vectorbt**: `fees`, `fixed_fees`, `slippage` on the constructor, or globally through
`vbt.settings['portfolio']`. These are proportional, so impact is not modelled. For a
size-dependent cost, precompute a slippage array per bar rather than a scalar.

**LEAN**: set the brokerage model, then attach a fee model, a slippage model and a fill
model per security through `set_security_initializer`.
`VolumeShareSlippageModel(volume_limit, price_impact)` is the honest default because it
caps participation and charges for it.

**Qlib**: `exchange_kwargs` with `open_cost`, `close_cost`, `min_cost`, `impact_cost`
and `limit_threshold`. `min_cost` matters for small orders in a large universe.

**ML4T**: the cost model lives in `setup.yaml`, and stage 17 runs the cost cascade
sweep. That is the reference implementation for cost sensitivity in this suite.

## Common mistakes

1. **A single basis-points number for every asset and every size.** Cost varies by
   liquidity, volatility and participation.
2. **Fills at the mid.** You cross the spread or you queue and sometimes miss.
3. **Fills outside the bar range.** A stop that fills exactly at the stop price during a
   gap is fiction.
4. **No participation cap.** A strategy taking 40% of a day's volume in a backtest is
   not describing a possible trade.
5. **Ignoring the borrow.** Hard-to-borrow shorts can cost 20% annually, and sometimes
   cannot be borrowed at all.
6. **Ignoring funding on perpetuals.** For crypto carry strategies the funding rate is
   frequently the entire return, positive or negative.
7. **Costing turnover at the signal frequency rather than at the rebalance frequency.**
   These differ, often by an order of magnitude.

## References

- Estimators, schedules and code: [playbook.md](references/playbook.md)

## Related skills

`portfolio-construction-risk` creates the turnover this skill prices,
`lean-algorithm-builder` for fill realism, `backtest-risk-audit` for the cost
sensitivity gate.
