"""
Strict t-1 bar-close feed.

The feed emits one *closed* bar at a time. At the moment a pod evaluates bar
``t`` it may see bars ``<= t`` (all of which have closed) and nothing later.
``get_closed_history()`` is the only history accessor pods receive; it can
never return a row whose close time is after the current decision time.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Optional, Union

import pandas as pd

from .arctic_store import OHLCV_COLUMNS, PointInTimeStore, _normalise_frame, parse_interval


class LookAheadError(RuntimeError):
    """Raised when a history frame contains data after the decision time."""


@dataclass(frozen=True)
class Bar:
    symbol: str
    timestamp: pd.Timestamp  # close time of the bar (UTC)
    open: float
    high: float
    low: float
    close: float
    volume: float
    open_time: Optional[pd.Timestamp] = None

    @property
    def close_time(self) -> pd.Timestamp:
        return self.timestamp

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(frozen=True)
class BarEvent:
    bar: Bar
    history: pd.DataFrame  # closed bars, last row == bar
    decision_time: pd.Timestamp


def assert_no_lookahead(history: pd.DataFrame, decision_time: pd.Timestamp) -> None:
    """Guard used by pods: every row in history must have closed by decision_time."""
    if history.empty:
        return
    latest = history.index.max()
    if latest > decision_time:
        raise LookAheadError(
            f"History contains bar closing at {latest} after decision time {decision_time}"
        )


class BarFeed:
    """
    Deterministic replay feed over a closed-bar frame.

    Parameters
    ----------
    symbol : str
    historical_df : DataFrame indexed by UTC timestamps.
    bar_interval : str or Timedelta, optional. Required when ``index_is_open_time`` is True.
    index_is_open_time : bool. If True the index is converted to close times.
    """

    def __init__(
        self,
        symbol: str,
        historical_df: pd.DataFrame,
        bar_interval: Optional[Union[str, pd.Timedelta]] = None,
        index_is_open_time: bool = False,
    ) -> None:
        self.symbol = symbol
        df = _normalise_frame(historical_df)
        self.bar_interval: Optional[pd.Timedelta] = parse_interval(bar_interval) if bar_interval else None
        if index_is_open_time:
            if self.bar_interval is None:
                raise ValueError("bar_interval is required when index_is_open_time=True")
            self._open_times = df.index
            df.index = df.index + self.bar_interval
            df.index.name = "timestamp"
        else:
            self._open_times = (df.index - self.bar_interval) if self.bar_interval is not None else None
        self.df = df
        self._current_idx = 0
        self._total_bars = len(self.df)

    @classmethod
    def from_store(
        cls,
        store: PointInTimeStore,
        symbol: str,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
    ) -> "BarFeed":
        df = store.read_range(symbol, start, end)
        if store.index_is_open_time:
            return cls(symbol, df, bar_interval=store.bar_interval, index_is_open_time=True)
        return cls(symbol, df, bar_interval=store.bar_interval)

    # ------------------------------------------------------------ iteration
    def __len__(self) -> int:
        return self._total_bars

    @property
    def position(self) -> int:
        return self._current_idx

    def has_next(self) -> bool:
        return self._current_idx < self._total_bars

    @property
    def decision_time(self) -> Optional[pd.Timestamp]:
        if self._current_idx == 0:
            return None
        return self.df.index[self._current_idx - 1]

    def peek_next_close_time(self) -> Optional[pd.Timestamp]:
        if not self.has_next():
            return None
        return self.df.index[self._current_idx]

    def _bar_at(self, idx: int) -> Bar:
        row = self.df.iloc[idx]
        ts = self.df.index[idx]
        open_time = self._open_times[idx] if self._open_times is not None else None
        return Bar(
            symbol=self.symbol,
            timestamp=ts,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            open_time=open_time,
        )

    def next_bar(self) -> Optional[Bar]:
        """Emit the next closed bar and advance the visible horizon."""
        if not self.has_next():
            return None
        bar = self._bar_at(self._current_idx)
        self._current_idx += 1
        return bar

    def next_event(self) -> Optional[BarEvent]:
        bar = self.next_bar()
        if bar is None:
            return None
        history = self.get_closed_history()
        return BarEvent(bar=bar, history=history, decision_time=bar.timestamp)

    def get_closed_history(self, lookback: Optional[int] = None) -> pd.DataFrame:
        """
        Closed bars up to and including the last emitted bar. Rows at or after
        the feed cursor are structurally unreachable.
        """
        visible = self.df.iloc[: self._current_idx]
        if lookback is not None and len(visible) > lookback:
            visible = visible.iloc[-lookback:]
        return visible.copy()

    def reset(self) -> None:
        self._current_idx = 0

    async def stream(self, pace_seconds: float = 0.0) -> AsyncIterator[BarEvent]:
        """Async replay; ``pace_seconds`` > 0 throttles emission for demos."""
        while self.has_next():
            event = self.next_event()
            assert event is not None
            yield event
            if pace_seconds > 0:
                await asyncio.sleep(pace_seconds)
            else:
                await asyncio.sleep(0)  # yield control to other pod workers


class QueueBarFeed:
    """
    Push-based feed for live operation: an exchange poller or WebSocket
    handler pushes *closed* bars; the pod worker consumes them in order.
    """

    def __init__(self, symbol: str, history: Optional[pd.DataFrame] = None, max_history: int = 5000) -> None:
        self.symbol = symbol
        self._queue: "asyncio.Queue[Optional[Bar]]" = asyncio.Queue()
        self.df = _normalise_frame(history) if history is not None and not history.empty else pd.DataFrame(
            columns=list(OHLCV_COLUMNS)
        )
        self.max_history = max_history

    async def push(self, bar: Bar) -> None:
        await self._queue.put(bar)

    async def close(self) -> None:
        await self._queue.put(None)

    def get_closed_history(self, lookback: Optional[int] = None) -> pd.DataFrame:
        visible = self.df
        if lookback is not None and len(visible) > lookback:
            visible = visible.iloc[-lookback:]
        return visible.copy()

    async def stream(self, pace_seconds: float = 0.0) -> AsyncIterator[BarEvent]:
        while True:
            bar = await self._queue.get()
            if bar is None:
                return
            if not self.df.empty and bar.timestamp <= self.df.index.max():
                continue  # duplicate or out-of-order bar: ignore
            row = pd.DataFrame(
                [[bar.open, bar.high, bar.low, bar.close, bar.volume]],
                columns=list(OHLCV_COLUMNS),
                index=pd.DatetimeIndex([bar.timestamp], name="timestamp"),
            )
            self.df = pd.concat([self.df, row]) if not self.df.empty else row
            if len(self.df) > self.max_history:
                self.df = self.df.iloc[-self.max_history :]
            yield BarEvent(bar=bar, history=self.df.copy(), decision_time=bar.timestamp)
