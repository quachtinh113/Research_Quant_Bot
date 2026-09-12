"""
Point-in-Time bar store.

Primary engine: ArcticDB (LMDB / S3 / file URIs). Fallback engine: Parquet
files read through Polars, so the same API behaves identically on Windows and
Linux boxes where ArcticDB wheels are unavailable.

The point-in-time contract
--------------------------
``read_as_of(symbol, as_of)`` returns only bars whose *close time* is
``<= as_of``. A bar that opened before ``as_of`` but has not yet closed is
invisible. Callers declare the index convention once at construction:

* ``index_is_open_time=False`` (default): the index is the bar close time.
* ``index_is_open_time=True``: the index is the bar open time and
  ``bar_interval`` is used to derive the close time.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd
from pandas.tseries.frequencies import to_offset

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def parse_interval(interval) -> pd.Timedelta:
    """Parse a bar interval ("5min", "1h", Timedelta) without NumPy generic-unit deprecation."""
    if isinstance(interval, pd.Timedelta):
        return interval
    return pd.Timedelta(to_offset(str(interval)).nanos, unit="ns")


def _to_utc(ts: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    return ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")


def _normalise_frame(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index must be a DatetimeIndex (UTC).")
    df = df.copy()
    df.index = df.index.tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
    df.index.name = "timestamp"
    df.columns = [str(c).lower() for c in df.columns]
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Bar frame missing columns: {missing}")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


class PointInTimeStore:
    """
    Zero-look-ahead bar store with ArcticDB primary and Parquet/Polars fallback.
    """

    def __init__(
        self,
        uri: str = "lmdb://./data_store",
        library_name: str = "market_data",
        fallback_dir: Optional[Path] = None,
        bar_interval: Optional[str] = None,
        index_is_open_time: bool = False,
        prefer_fallback: bool = False,
    ) -> None:
        self.uri = uri
        self.library_name = library_name
        self.bar_interval: Optional[pd.Timedelta] = parse_interval(bar_interval) if bar_interval else None
        self.index_is_open_time = index_is_open_time
        if index_is_open_time and self.bar_interval is None:
            raise ValueError("bar_interval is required when index_is_open_time=True")

        root = Path(fallback_dir) if fallback_dir is not None else Path("./data_store")
        self._fallback_dir = root / library_name
        self._arctic = None
        self._library = None
        self.backend_type = "ParquetPointInTime"
        if not prefer_fallback:
            self._init_arctic()
        if self.backend_type != "ArcticDB":
            self._fallback_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ setup
    def _init_arctic(self) -> None:
        try:
            import arcticdb as adb  # type: ignore

            self._arctic = adb.Arctic(self.uri)
            if self.library_name not in self._arctic.list_libraries():
                self._library = self._arctic.create_library(self.library_name)
            else:
                self._library = self._arctic[self.library_name]
            self.backend_type = "ArcticDB"
        except ImportError:
            logger.info("arcticdb not installed; using Parquet/Polars point-in-time fallback.")
        except Exception as exc:  # pragma: no cover - environment specific
            logger.warning("ArcticDB init failed (%s); using Parquet fallback.", exc)

    def _file_for(self, symbol: str) -> Path:
        safe = symbol.replace("/", "_").replace(":", "_")
        return self._fallback_dir / f"{safe}.parquet"

    # ------------------------------------------------------------------ write
    def write_bars(self, symbol: str, df: pd.DataFrame, prune_previous: bool = False) -> int:
        """Append (or replace) bars. Returns the number of rows now stored."""
        df = _normalise_frame(df)
        if self.backend_type == "ArcticDB" and self._library is not None:
            if prune_previous or not self._library.has_symbol(symbol):
                self._library.write(symbol, df)
            else:
                existing = self._library.read(symbol).data
                combined = pd.concat([existing, df])
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                self._library.write(symbol, combined)
            return int(len(self._library.read(symbol).data))

        path = self._file_for(symbol)
        if path.exists() and not prune_previous:
            existing = pd.read_parquet(path)
            existing = _normalise_frame(existing)
            df = pd.concat([existing, df])
            df = df[~df.index.duplicated(keep="last")].sort_index()
        df.to_parquet(path)
        return int(len(df))

    # ------------------------------------------------------------------- read
    def _read_all(self, symbol: str) -> pd.DataFrame:
        if self.backend_type == "ArcticDB" and self._library is not None:
            if not self._library.has_symbol(symbol):
                return pd.DataFrame(columns=list(OHLCV_COLUMNS))
            return _normalise_frame(self._library.read(symbol).data)

        path = self._file_for(symbol)
        if not path.exists():
            return pd.DataFrame(columns=list(OHLCV_COLUMNS))
        try:
            import polars as pl  # type: ignore

            lf = pl.scan_parquet(path)
            pdf = lf.collect().to_pandas()
            if "timestamp" in pdf.columns:
                pdf = pdf.set_index("timestamp")
            return _normalise_frame(pdf)
        except ImportError:  # pragma: no cover
            return _normalise_frame(pd.read_parquet(path))

    def close_times(self, index: pd.DatetimeIndex) -> pd.DatetimeIndex:
        if self.index_is_open_time:
            return index + self.bar_interval
        return index

    def read_as_of(
        self,
        symbol: str,
        as_of: pd.Timestamp,
        lookback_bars: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Bars whose close time is <= as_of. Future bars are never returned.
        """
        as_of = _to_utc(as_of)
        data = self._read_all(symbol)
        if data.empty:
            return data
        closes = self.close_times(data.index)
        data = data[closes <= as_of]
        if lookback_bars is not None and len(data) > lookback_bars:
            data = data.iloc[-lookback_bars:]
        return data.copy()

    def read_range(
        self,
        symbol: str,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
    ) -> pd.DataFrame:
        """Inclusive range on the index (research use; not point-in-time safe)."""
        data = self._read_all(symbol)
        if start is not None:
            data = data[data.index >= _to_utc(start)]
        if end is not None:
            data = data[data.index <= _to_utc(end)]
        return data.copy()

    def list_symbols(self) -> List[str]:
        if self.backend_type == "ArcticDB" and self._library is not None:
            return sorted(self._library.list_symbols())
        return sorted(p.stem.replace("_", "/", 1) for p in self._fallback_dir.glob("*.parquet"))

    def delete(self, symbol: str) -> None:
        if self.backend_type == "ArcticDB" and self._library is not None:
            if self._library.has_symbol(symbol):
                self._library.delete(symbol)
            return
        path = self._file_for(symbol)
        if path.exists():
            path.unlink()
