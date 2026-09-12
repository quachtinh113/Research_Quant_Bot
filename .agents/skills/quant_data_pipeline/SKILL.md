---
name: quant-data-pipeline
description: "Build data layers that cannot leak: point-in-time fundamentals, corporate-action adjustment, survivorship-free universes, bar sampling, calendars, and the storage formats each repository expects."
---

# Point-in-Time Data Pipelines

Most fake alpha is a data bug. Not a modelling mistake, a data bug: a value that was
not knowable when the model claims to have used it. This skill is about building the
data layer so that class of error cannot occur.

## The one question

For every value in your dataset: **when did this become knowable, and is that
timestamp what the pipeline uses?**

Three timestamps travel with every observation, and confusing them is the whole
problem.

| Timestamp | Meaning | Example |
|---|---|---|
| **Event time** | when the thing happened | the quarter a company earned the revenue |
| **Publication time** | when it was first released | the 10-Q filing datetime |
| **Vintage** | the version you are reading | the restated figure published two years later |

A model may use only values whose **publication time** is before the decision. A
dataset indexed by event time and populated with the latest vintage is the single most
common source of impossible backtest results.

## Bitemporal storage

Store two time axes and the problem solves itself.

```text
(entity, event_date, published_at, value)
```

Then the point-in-time query is mechanical:

```sql
SELECT DISTINCT ON (entity, event_date) entity, event_date, value
FROM fundamentals
WHERE published_at <= :as_of
ORDER BY entity, event_date, published_at DESC;
```

If your vendor does not supply `published_at`, you do not have point-in-time data.
Approximating it with "event date plus 45 days" is a hack, and it should be labelled
as one in the code, not buried.

Sources that do supply it: SEC EDGAR through `edgartools` or `datamule-python`, ALFRED
for revised macro series, and the ML4T `04_fundamental_alternative_data` chapter's
bitemporal loaders. `pit-adjuster` and `pit-release-gate` in the awesome-quant index
exist for the same reason.

## Survivorship

A universe built from today's index members contains only companies that survived.
Backtests on it earn a return nobody could have earned.

What is needed:

1. **Historical membership**, with the add and remove dates for every constituent.
2. **Delisted securities** kept in the database with their final prices.
3. **A terminal return** for each delisting: bankruptcy is roughly −100%, an
   acquisition is the deal price. Dropping the row instead silently deletes a loss.
4. **Symbol mapping over time**, so a ticker reused by a different company does not
   splice two histories together.

The diagnostic: count the names in your universe by year. If the count rises smoothly
and no name ever leaves, you have a survivorship problem. ML4T's
`02_financial_data_universe/15_survivorship_bias_detection.py` implements the check.

## Corporate actions

Adjusted prices are convenient and dangerous. A back-adjusted series is recomputed
every time a new split or dividend occurs, so the price you see today for 2015 is not
the price you would have seen in 2015.

Rules:

- Store **raw** prices plus an **adjustment factor time series**. Adjust at query time
  using only factors known as of the query date.
- Never use a back-adjusted series to decide whether a price crossed a level.
- Charge the dividend as cash if you are modelling total return, rather than folding
  it into price.
- For futures, state the roll rule (calendar, open interest, volume), and charge the
  roll spread. A back-adjusted continuous contract with no roll cost is fiction.

## Bars

The bar you choose changes the statistical properties of everything downstream.

| Bar type | Sampling rule | Property |
|---|---|---|
| Time | fixed clock interval | familiar; heteroskedastic; oversamples quiet periods |
| Tick | fixed number of trades | closer to information arrival |
| Volume | fixed traded quantity | returns closer to normal |
| Dollar | fixed traded notional | stable across price-level changes; usually the best default |
| Imbalance | cumulative signed flow threshold | event-driven, adapts to activity |

Dollar bars are the standard recommendation for machine-learning work because they
keep the information content per bar roughly constant as prices and volumes change
over years. ML4T's `03_market_microstructure` chapter builds all of these.

## Calendars

Trading calendars are a correctness issue, not a convenience.

- Use `exchange_calendars` or `pandas_market_calendars`. Do not hand-roll holidays.
- Half-days exist and have different volume profiles.
- Multi-venue strategies need timezone-aware alignment, and "aligned on date" is not
  the same as "aligned on time" across sessions.
- Crypto trades continuously, so a daily bar has an arbitrary cut. State which one and
  keep it consistent, because funding, settlement and your bar boundary interact.

## Quality gates before modelling

Run these on every dataset and fail loudly.

- **OHLC invariants**: `low <= min(open, close)`, `high >= max(open, close)`,
  `high >= low`, all prices positive.
- **Volume**: non-negative, and zero-volume bars flagged rather than silently kept.
- **Gaps**: count missing sessions against the exchange calendar.
- **Duplicates**: no two rows for one `(entity, timestamp)`.
- **Outliers**: returns beyond, say, 20 standard deviations are usually a bad print or
  an unadjusted split, not a market event.
- **Staleness**: a price repeating unchanged for many bars is often a dead feed.
- **Timezone**: index is timezone-aware and in a stated zone.

ML4T's `utils/data_quality.py` provides `validate_prices`, `validate_labels`,
`validate_features`, `validate_modeling_inputs` and `check_ohlc_invariants`.

## Storage

| Format | Use it for |
|---|---|
| Parquet | the default for panel data; columnar, compressed, typed |
| Arrow / Polars | in-memory analytics on large panels |
| ArcticDB | versioned tick and time-series storage at scale |
| HDF5 | legacy; workable but poor concurrency |
| SQLite | run logs, registries, metadata; not bulk bars |
| CSV | interchange only, never a working store |

Partition by date and, for wide panels, by entity. Store the schema and the vendor
version alongside the data.

## Vendor selection

Beyond price, ask: does it provide publication timestamps, does it include delisted
securities, how are corporate actions represented, what is the revision policy, and
what happens to your history if you stop paying? A vendor that cannot answer the first
two is a vendor for exploration, not for research you intend to trade.

## References

- Procedures and code: [playbook.md](references/playbook.md)

## Related skills

`awesome-quant-curator` for the vendor inventory, `alpha-research-workflow` for what
happens after the data is clean, `backtest-risk-audit` for detecting the failures this
skill prevents.
