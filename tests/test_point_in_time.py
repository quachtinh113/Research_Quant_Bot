"""
Point-in-time discipline: zero look-ahead in the store, the feed and the pod.
"""

import asyncio

import pandas as pd
import pytest

from orchestration.data.arctic_store import PointInTimeStore, parse_interval
from orchestration.data.bar_feed import Bar, BarFeed, LookAheadError, QueueBarFeed, assert_no_lookahead
from orchestration.pod.sample_pod import VolatilityBreakoutPod
from tests.conftest import make_ohlcv


# ----------------------------------------------------------------- BarFeed
def test_bar_feed_lookahead_prevention():
    df = make_ohlcv(30)
    feed = BarFeed(symbol="BTC/USDT", historical_df=df)
    assert len(feed) == 30
    assert len(feed.get_closed_history()) == 0
    assert feed.decision_time is None

    emitted = [feed.next_bar() for _ in range(5)]
    history = feed.get_closed_history()
    assert len(history) == 5
    assert history.index[-1] == emitted[-1].timestamp
    assert feed.decision_time == emitted[-1].timestamp
    assert df.index[5] not in history.index
    assert history.index.max() < feed.peek_next_close_time()


def test_bar_feed_open_time_convention_shifts_to_close_time():
    df = make_ohlcv(10, freq="5min")  # treat index as OPEN times
    feed = BarFeed("XAU/USD", df, bar_interval="5min", index_is_open_time=True)
    bar = feed.next_bar()
    assert bar.open_time == df.index[0]
    assert bar.timestamp == df.index[0] + parse_interval("5min")
    assert feed.get_closed_history().index[-1] == bar.timestamp


def test_assert_no_lookahead_raises_on_leak():
    df = make_ohlcv(10)
    with pytest.raises(LookAheadError):
        assert_no_lookahead(df, df.index[3])
    assert_no_lookahead(df.iloc[:4], df.index[3])  # exact boundary is allowed


def test_queue_feed_ignores_out_of_order_bars():
    async def _run():
        feed = QueueBarFeed("BTC/USDT")
        t0 = pd.Timestamp("2026-01-01 00:05", tz="UTC")
        mk = lambda ts, c: Bar("BTC/USDT", ts, c, c + 1, c - 1, c, 10.0)  # noqa: E731
        await feed.push(mk(t0, 100.0))
        await feed.push(mk(t0 + parse_interval("5min"), 101.0))
        await feed.push(mk(t0, 99.0))  # stale duplicate must be dropped
        await feed.close()
        seen = [ev async for ev in feed.stream()]
        assert [ev.bar.close for ev in seen] == [100.0, 101.0]
        assert seen[-1].history.index.is_monotonic_increasing
        assert seen[-1].history.index.max() == seen[-1].decision_time

    asyncio.run(_run())


# -------------------------------------------------------------------- Store
def test_point_in_time_store_as_of(tmp_path):
    df = make_ohlcv(20)
    store = PointInTimeStore(uri=f"lmdb://{tmp_path}/arctic", library_name="pit", fallback_dir=tmp_path)
    store.write_bars("ETH/USDT", df, prune_previous=True)

    cutoff = df.index[10]
    result = store.read_as_of("ETH/USDT", as_of=cutoff)
    assert len(result) == 11
    assert result.index.max() == cutoff
    assert result.index.max() < df.index[11]

    # A timestamp between two closes must not reveal the later bar.
    between = df.index[10] + parse_interval("2min")
    assert len(store.read_as_of("ETH/USDT", as_of=between)) == 11
    assert len(store.read_as_of("ETH/USDT", as_of=cutoff, lookback_bars=3)) == 3


def test_store_open_time_convention_excludes_unclosed_bar(tmp_path):
    df = make_ohlcv(20, freq="5min")  # index = open times
    store = PointInTimeStore(
        uri=f"lmdb://{tmp_path}/arctic", library_name="pit_open", fallback_dir=tmp_path,
        bar_interval="5min", index_is_open_time=True,
    )
    store.write_bars("BTC/USDT", df, prune_previous=True)
    as_of = df.index[10] + parse_interval("3min")  # bar 10 is still forming
    res = store.read_as_of("BTC/USDT", as_of=as_of)
    assert len(res) == 10  # bars 0..9 closed (bar 9 closes at open[10])
    assert res.index.max() == df.index[9]


def test_store_append_dedups_and_sorts(tmp_path):
    df = make_ohlcv(10)
    store = PointInTimeStore(fallback_dir=tmp_path, library_name="append")
    store.write_bars("BTC/USDT", df.iloc[:6], prune_previous=True)
    n = store.write_bars("BTC/USDT", df.iloc[4:])  # overlapping append
    assert n == 10
    out = store.read_as_of("BTC/USDT", df.index[-1])
    assert len(out) == 10 and out.index.is_monotonic_increasing and out.index.is_unique
    assert "BTC/USDT" in store.list_symbols()


# ---------------------------------------------------------------------- Pod
def test_pod_never_receives_future_bars():
    """Every history frame handed to alpha code ends exactly at the bar close."""
    df = make_ohlcv(40, base=1000.0, drift=1.0, vol=2.0)
    feed = BarFeed("BTC/USDT", df)
    pod = VolatilityBreakoutPod(instance_id="PIT_POD", symbol="BTC/USDT", lookback_period=10)
    seen = []
    orig = pod.generate_signal

    def spy(history, bar):
        seen.append((history.index.max(), bar.timestamp, feed.peek_next_close_time()))
        return orig(history, bar)

    pod.generate_signal = spy  # type: ignore[assignment]

    async def _run():
        await pod.run(feed)

    asyncio.run(_run())
    assert len(seen) == 40
    for hist_max, bar_ts, next_close in seen:
        assert hist_max == bar_ts
        if next_close is not None:
            assert hist_max < next_close


def test_pod_rejects_leaked_history():
    df = make_ohlcv(20)
    pod = VolatilityBreakoutPod(instance_id="LEAK_POD", symbol="BTC/USDT", lookback_period=5)
    bar = Bar("BTC/USDT", df.index[5], 1, 2, 0.5, 1.5, 10.0)

    async def _run():
        with pytest.raises(LookAheadError):
            await pod.on_bar(bar, df)  # full frame leaks bars 6..19

    asyncio.run(_run())
