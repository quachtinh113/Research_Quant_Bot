"""
Shared synthetic market data generators for the orchestration test suite.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_ohlcv(
    bars: int = 50,
    freq: str = "5min",
    base: float = 100.0,
    drift: float = 0.0,
    vol: float = 0.5,
    seed: int = 42,
    start: str = "2026-01-01 00:00:00",
) -> pd.DataFrame:
    """Random-walk OHLCV indexed by bar close time (UTC)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=bars, freq=freq, tz="UTC")
    close = base + np.cumsum(rng.normal(drift, vol, bars))
    high = close + rng.uniform(0.1, 1.0, bars)
    low = close - rng.uniform(0.1, 1.0, bars)
    open_p = close + rng.uniform(-0.5, 0.5, bars)
    volume = rng.uniform(10, 100, bars)
    return pd.DataFrame({"open": open_p, "high": high, "low": low, "close": close, "volume": volume}, index=dates)


def make_breakout_then_crash(
    quiet_bars: int = 16,
    base: float = 100.0,
    breakout_close: float = 103.0,
    crash_open: float = 80.0,
    after_bars: int = 5,
    freq: str = "5min",
    start: str = "2026-02-01 00:00:00",
) -> pd.DataFrame:
    """
    Deterministic scenario: tight range -> upside breakout bar -> gap crash bar
    -> a few quiet bars. Bar index ``quiet_bars`` is the breakout; the next bar
    is the crash.
    """
    rows = []
    for i in range(quiet_bars):
        c = base + 0.2 * ((-1) ** i)
        rows.append((c - 0.1, c + 0.3, c - 0.3, c, 50.0))
    rows.append((base + 0.2, breakout_close + 0.2, base, breakout_close, 120.0))  # breakout
    rows.append((crash_open, crash_open + 1.0, crash_open - 2.0, crash_open - 1.0, 400.0))  # crash
    for i in range(after_bars):
        c = crash_open - 1.0 + 0.1 * ((-1) ** i)
        rows.append((c - 0.1, c + 0.3, c - 0.3, c, 50.0))
    dates = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=dates)


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    return make_ohlcv(50)


@pytest.fixture
def breakout_crash_df() -> pd.DataFrame:
    return make_breakout_then_crash()
