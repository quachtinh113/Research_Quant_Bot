# Data Pipeline Playbook

## 1. A bitemporal store in SQLite

```python
import sqlite3
from contextlib import closing

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    entity       TEXT    NOT NULL,
    field        TEXT    NOT NULL,
    event_date   TEXT    NOT NULL,   -- when the fact refers to
    published_at TEXT    NOT NULL,   -- when it became knowable
    value        REAL,
    vendor       TEXT,
    PRIMARY KEY (entity, field, event_date, published_at)
);
CREATE INDEX IF NOT EXISTS idx_pit ON observations (entity, field, published_at);
"""


def as_of(conn, field, as_of_ts):
    """Latest value per (entity, event_date) that was published on or before as_of."""
    return conn.execute(
        """
        SELECT entity, event_date, value
        FROM observations o
        WHERE field = ? AND published_at <= ?
          AND published_at = (
              SELECT MAX(published_at) FROM observations i
              WHERE i.entity = o.entity AND i.field = o.field
                AND i.event_date = o.event_date AND i.published_at <= ?
          )
        """,
        (field, as_of_ts, as_of_ts),
    ).fetchall()
```

Inserting a restatement adds a row rather than updating one. History stays intact and
the point-in-time query keeps working.

## 2. Detect the vintage problem

```python
def restatement_report(conn, field):
    rows = conn.execute(
        """SELECT entity, event_date, COUNT(*) AS versions,
                  MIN(value) AS first_seen, MAX(value) AS last_seen
           FROM observations WHERE field = ?
           GROUP BY entity, event_date HAVING COUNT(*) > 1""",
        (field,),
    ).fetchall()
    return rows
```

If a large share of observations have multiple versions, any model built on the latest
vintage is reading the future. Quantify it before arguing about it.

## 3. Survivorship-free universe

```python
import pandas as pd


def universe_as_of(membership: pd.DataFrame, date) -> list:
    """membership columns: entity, start_date, end_date (NaT while still a member)."""
    d = pd.Timestamp(date)
    active = membership[(membership["start_date"] <= d) &
                        (membership["end_date"].isna() | (membership["end_date"] > d))]
    return sorted(active["entity"].unique())


def apply_delisting_returns(returns: pd.DataFrame,
                            delistings: pd.DataFrame) -> pd.DataFrame:
    """delistings columns: entity, delist_date, terminal_return."""
    out = returns.copy()
    for row in delistings.itertuples():
        if row.entity in out.columns and row.delist_date in out.index:
            out.loc[row.delist_date, row.entity] = row.terminal_return
            out.loc[out.index > row.delist_date, row.entity] = pd.NA
    return out
```

A bankruptcy with no terminal return is a loss you deleted. Default to −1.0 when the
vendor gives nothing, and say so.

## 4. Survivorship diagnostic

```python
def survivorship_check(universe_by_date: dict) -> dict:
    dates = sorted(universe_by_date)
    counts = {d: len(universe_by_date[d]) for d in dates}
    exits = sum(
        len(set(universe_by_date[a]) - set(universe_by_date[b]))
        for a, b in zip(dates, dates[1:])
    )
    return {
        "first_count": counts[dates[0]], "last_count": counts[dates[-1]],
        "total_exits": exits,
        "suspicious": exits == 0,
        "note": ("no name ever left the universe, which does not happen in real markets"
                 if exits == 0 else "exits present"),
    }
```

## 5. Adjustment factors applied as of a date

```python
import numpy as np
import pandas as pd


def adjusted_close(raw_close: pd.Series, actions: pd.DataFrame,
                   as_of: pd.Timestamp) -> pd.Series:
    """actions columns: ex_date, split_ratio, dividend. Only actions known by
    as_of are applied, so the series matches what was observable then."""
    known = actions[actions["ex_date"] <= as_of].sort_values("ex_date")
    factor = pd.Series(1.0, index=raw_close.index)
    for row in known.itertuples():
        mask = raw_close.index < row.ex_date
        if row.split_ratio and row.split_ratio != 1:
            factor[mask] /= row.split_ratio
        if row.dividend:
            prev = raw_close[raw_close.index < row.ex_date]
            if len(prev):
                factor[mask] *= (1 - row.dividend / prev.iloc[-1])
    return raw_close * factor
```

Calling this with two different `as_of` values and diffing the result shows exactly
how much a back-adjusted series rewrites history.

## 6. Bars

```python
import numpy as np
import pandas as pd


def dollar_bars(ticks: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """ticks: index=datetime, columns=[price, size]."""
    notional = (ticks["price"] * ticks["size"]).to_numpy()
    cum, rows, start = 0.0, [], 0
    for i, v in enumerate(notional):
        cum += v
        if cum >= threshold:
            seg = ticks.iloc[start:i + 1]
            rows.append({
                "timestamp": seg.index[-1],
                "open": float(seg["price"].iloc[0]),
                "high": float(seg["price"].max()),
                "low": float(seg["price"].min()),
                "close": float(seg["price"].iloc[-1]),
                "volume": float(seg["size"].sum()),
                "dollar": float(cum), "ticks": len(seg),
            })
            cum, start = 0.0, i + 1
    return pd.DataFrame(rows).set_index("timestamp")


def tick_rule(prices: np.ndarray) -> np.ndarray:
    """Lee-Ready style trade sign when no quotes are available."""
    d = np.diff(prices, prepend=prices[0])
    signs = np.sign(d)
    for i in range(1, len(signs)):
        if signs[i] == 0:
            signs[i] = signs[i - 1]
    return np.where(signs == 0, 1.0, signs)
```

Set the dollar threshold so you get a workable number of bars per day, then keep it
fixed across the study. Changing it mid-research changes every statistic.

## 7. Quality gates

```python
import numpy as np
import pandas as pd


def validate_ohlcv(df: pd.DataFrame, calendar_sessions=None) -> dict:
    issues = []
    required = {"open", "high", "low", "close", "volume"}
    missing = required - {c.lower() for c in df.columns}
    if missing:
        issues.append(f"missing columns: {sorted(missing)}")
        return {"ok": False, "issues": issues}

    d = df.rename(columns=str.lower)
    bad_hl = (d["high"] < d["low"]).sum()
    bad_o = (d["open"] > d["high"]) | (d["open"] < d["low"])
    bad_c = (d["close"] > d["high"]) | (d["close"] < d["low"])
    nonpos = (d[["open", "high", "low", "close"]] <= 0).any(axis=1).sum()
    negvol = (d["volume"] < 0).sum()
    dupes = int(d.index.duplicated().sum())

    r = d["close"].pct_change()
    z = (r - r.mean()) / (r.std(ddof=1) + 1e-12)
    outliers = int((z.abs() > 20).sum())
    stale = int((d["close"].diff() == 0).rolling(5).sum().max() or 0)

    for label, n in (("high<low", bad_hl), ("open outside range", bad_o.sum()),
                     ("close outside range", bad_c.sum()),
                     ("non-positive price", nonpos), ("negative volume", negvol),
                     ("duplicate timestamps", dupes),
                     ("returns beyond 20 sigma", outliers)):
        if n:
            issues.append(f"{label}: {int(n)}")
    if stale >= 5:
        issues.append(f"price unchanged for {stale} consecutive bars")
    if getattr(d.index, "tz", None) is None:
        issues.append("index is timezone-naive")
    if calendar_sessions is not None:
        gaps = len(set(calendar_sessions) - set(d.index.normalize()))
        if gaps:
            issues.append(f"missing sessions vs calendar: {gaps}")

    return {"ok": not issues, "issues": issues, "rows": len(d)}
```

Fail the pipeline on `ok is False`. A warning that scrolls past is a warning nobody
acts on.

## 8. Calendars

```python
import exchange_calendars as xcals

nyse = xcals.get_calendar("XNYS")
sessions = nyse.sessions_in_range("2015-01-01", "2024-12-31")
half_days = [s for s in sessions if nyse.session_close(s).hour < 16]

open_ts = nyse.session_open("2024-07-03")
close_ts = nyse.session_close("2024-07-03")     # early close
```

For a multi-venue strategy, align on UTC timestamps and record each venue's session
boundaries. Aligning on calendar date across Tokyo and New York compares different
days.

## 9. Futures rolls

```python
import pandas as pd


def roll_series(contracts: dict, rule: str = "open_interest") -> pd.DataFrame:
    """contracts: {symbol: DataFrame[open, high, low, close, volume, open_interest]}.
    Returns the front-month series plus the roll cost actually incurred."""
    frames = []
    for sym, df in contracts.items():
        f = df.copy()
        f["symbol"] = sym
        frames.append(f)
    panel = pd.concat(frames).sort_index()

    key = "open_interest" if rule == "open_interest" else "volume"
    front = panel.groupby(level=0).apply(lambda g: g.loc[g[key].idxmax()])
    front["rolled"] = front["symbol"] != front["symbol"].shift(1)
    front["roll_cost"] = 0.0
    for ts in front.index[front["rolled"]]:
        prev_sym = front["symbol"].shift(1).loc[ts]
        if isinstance(prev_sym, str) and prev_sym in contracts:
            old = contracts[prev_sym]["close"].get(ts)
            new = contracts[front.loc[ts, "symbol"]]["close"].get(ts)
            if old and new:
                front.loc[ts, "roll_cost"] = float(new - old)
    return front
```

Charge `roll_cost` in the backtest. A back-adjusted continuous series with the roll
folded into the price makes a carry cost look like alpha.

## 10. Loading through ML4T

```python
from data import (
    load_etfs, load_us_equities, load_sp500_daily_bars, load_crypto_perps,
    load_fx_pairs, load_cme_futures, load_macro, load_ff_factors,
    DataNotFoundError, MissingDependencyError,
)

try:
    prices = load_etfs()
except DataNotFoundError:
    ...   # run data/download_all.py first
```

These loaders already apply the point-in-time and quality rules above. Prefer them
over ad-hoc downloads whenever the work lives in that repository.
