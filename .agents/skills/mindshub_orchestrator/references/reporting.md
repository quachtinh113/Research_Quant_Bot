# Reporting and Tear Sheets

## What the generated report contains

`QuantReportGenerator.generate_html_summary` writes a single self-contained HTML file
with no external assets, so it opens anywhere and can be emailed or attached.

Sections, in order:

1. **Header** — goal, asset, generation timestamp in UTC, and a verdict badge coloured
   green for an approval and amber otherwise.
2. **Provenance banner** — rendered only when the run used synthetic prices. It states
   plainly that nothing below is evidence about a strategy.
3. **Performance table** — the metrics in `_METRIC_ROWS` formatted by type, with any
   additional scalar keys appended so nothing the builder produced is silently dropped.
4. **Mentor audit** — verdict, institutional score if present, and the strengths,
   critiques and recommendations as lists.
5. **Strategy blueprint** — the mentor's design as formatted JSON.
6. **Stage panels** — one per collaboration step, with the agent, the role and the raw
   output, so a reader can check any number against its source.
7. **Footer** — a standing reminder that costs, slippage and the trial count must be
   stated before the report is used for a decision.

## Extending it

The metric rows are a module-level tuple:

```python
_METRIC_ROWS = (
    ("total_return", "Total Return", "pct"),
    ("sharpe_ratio", "Sharpe Ratio", "num"),
    ...
)
```

Add a row by appending `(key, label, kind)` where `kind` is `"pct"`, `"num"` or
`"int"`. Keys not listed still appear, unformatted, in the same table.

To add a chart without taking a dependency, emit inline SVG. A minimal equity curve:

```python
def _equity_svg(values, width=640, height=180):
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = width / (len(values) - 1)
    pts = " ".join(
        f"{i * step:.1f},{height - (v - lo) / span * height:.1f}"
        for i, v in enumerate(values)
    )
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
            f'role="img" aria-label="Equity curve">'
            f'<polyline fill="none" stroke="#38bdf8" stroke-width="2" points="{pts}"/>'
            f"</svg>")
```

Give every chart a `role="img"` and an `aria-label`, use `viewBox` with a percentage
width so it scales, and pick colours that survive both light and dark rendering.

## What an institutional tear sheet should carry

If you extend this into a full tear sheet, these are the elements that matter, roughly
in order of how often their absence causes a bad decision.

**Provenance and scope** — data source, date range, universe, rebalance cadence, the
cost assumption in basis points, and the number of configurations tested. Without the
trial count, no significance statement is possible.

**Return and risk** — CAGR, annualised volatility, Sharpe, Sortino, Calmar, maximum
drawdown with its start, trough and recovery dates, and time under water. Report the
drawdown duration, not only its depth: a 15% drawdown that recovers in two months and
one that takes three years are different products.

**Cost sensitivity** — Sharpe as a function of the assumed cost, from zero to roughly
three times your estimate. The point where it crosses zero is the strategy's real
margin of safety. This single chart disqualifies more strategies than any other.

**Turnover and capacity** — annual turnover, average holding period, and the notional
at which participation exceeds a sensible fraction of daily volume.

**Exposure** — gross and net exposure over time, and the factor loadings if the
universe has any structure. A "market neutral" strategy with a 0.6 beta is a levered
long position with extra steps.

**Distribution** — monthly return heat map, the worst ten periods, skew and kurtosis,
and the contribution of the best and worst trades. If removing the five best trades
turns the result negative, the strategy is a lottery ticket.

**Statistical significance** — the Deflated Sharpe Ratio given the trial count, and
the probability of backtest overfitting if a combinatorial split was run. See
`backtest-risk-audit`.

**Out-of-sample separation** — which numbers came from the training window, which from
validation, and which from the holdout. Label every panel. A tear sheet that mixes
them is decoration.

## Alternatives worth using instead of building your own

If you need a full tear sheet quickly, `quantstats` produces one from a return series
in a line, and `pyfolio-reloaded` gives the classic Quantopian layout. Both are in the
awesome-quant index. Use the MindsHub generator when you want the agent verdict and
provenance banner alongside the metrics, which those libraries do not model.

## PDF output

There is no PDF path in `report_generator.py`. Two scripts at the repository root,
`make_pdf.py` and `generate_v9_institutional_pdf.py`, produce PDFs from HTML. If you
need PDF from a pipeline run, generate the HTML first and pass it to one of those,
rather than adding a rendering dependency to the report generator.
