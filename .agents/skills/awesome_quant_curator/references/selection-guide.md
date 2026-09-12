# Choosing Between Candidates

A recommendation is only useful if it survives contact with the actual problem. Work
through these before naming a package.

## 1. Establish the shape of the problem

| Question | Why it changes the answer |
|---|---|
| Asset class? | Options need a pricing library, crypto needs venue connectors, futures need roll handling |
| Frequency? | Daily is pandas or Polars territory; tick and order book is Numba, Rust or C++ territory |
| Cross-section or single instrument? | Ranking many names points to Qlib; timing one points to vectorbt or LEAN |
| Research or production? | A research library that has never run live is a different risk than a broker SDK |
| Who maintains it after you? | A niche package with one contributor is a liability in a production stack |

## 2. Apply the elimination filters in order

**Licence.** Check the project's own licence, not the list's. Common traps in this
space: Apache 2.0 with the **Commons Clause** (vectorbt), AGPL, "free for
non-commercial use", and free API tiers whose limits change without notice. If the
work will be sold or run for clients, this filter comes first.

**Maintenance.** The list's own gate is commits within twelve months plus a README
with usage examples. Anything in **Historical & Archived Projects** has explicitly
failed that. Check the repository directly rather than trusting a star count.

**Dependency weight.** A package that pulls TensorFlow to compute a moving average is
a bad trade. In this suite specifically, adding a second dataframe library or a fourth
backtester costs more than it returns.

**Overlap with what is already here.** Qlib, vectorbt, LEAN and the ML4T utilities
already cover data handling, factor construction, simulation, portfolio construction
and reporting. Reach outside only when there is a capability gap, and say what the gap
is.

## 3. Common decisions, with the trade-off stated

### Backtesting engine

| Candidate | Choose it when | Cost |
|---|---|---|
| `vectorbt` | parameter sweeps, fast iteration, signal-level research | no order book, no partial fills, Commons Clause |
| `Lean` | fill realism, options and futures chains, live parity, many brokers | C# core, heavyweight setup, needs data |
| `nautilus_trader` | high-frequency Python with a Rust core, event-driven and fast | smaller ecosystem, steeper learning curve |
| `backtrader` | simple, pure Python, large community of examples | unmaintained upstream; use the cloudQuant fork |
| `zipline-reloaded` | pipeline API, US equity fundamentals workflows | opinionated data bundles |
| `hftbacktest` | queue position and latency actually matter | needs order-book data you probably do not have |
| `Backtesting.py` | a single-instrument idea in twenty lines | too limited for a portfolio |

### Portfolio optimiser

| Candidate | Choose it when |
|---|---|
| ML4T `allocation.py` | you are already inside a case study; HRP, MVO, risk parity, inverse vol, conformal |
| `Riskfolio-Lib` | you need many risk measures and constraint types out of the box |
| `skfolio` | you want a scikit-learn API with cross-validation over allocators |
| `PyPortfolioOpt` | you want the classical frontier with readable code |
| `fortitudo.tech` | you need CVaR optimisation or entropy pooling on views |
| `riskparity.py` | large-scale risk parity specifically |

### Factor evaluation

`alphalens-reloaded` for the classic tear sheet, `Spectre` when the factor universe is
large enough to need a GPU, `factor-qc` or `Perception-XAlpha Lite` when you want the
statistical gate (deflated Sharpe, PBO, White's Reality Check) rather than the
descriptive report, `Lacuna` or `lookahead-free` when the question is whether the
pipeline leaks at all.

### Market data

Start from what the ML4T `data/` loaders already provide. Beyond that:

| Need | Candidates |
|---|---|
| Free daily equities | `yfinance`, `yahooquery`, `FinanceDataReader` |
| Paid US equities and options | `polygon.io`, `tiingo`, `alpaca-trade-api` |
| SEC filings and fundamentals | `edgartools`, `datamule-python`, `edgar-sec` |
| Macro | `fedfred`, `pystlouisfed`, `FRB`, `pandaSDMX` |
| Crypto OHLCV | `ccxt`, `pricehub` |
| Crypto tick and order book | `tardis-python`, `lake-api` |
| China A-shares | `akshare`, `tushare`, `cn_stock_src` |
| Trading calendars | `exchange_calendars`, `pandas_market_calendars` |
| Institutional terminal | `pdblp`, `pybbg` for Bloomberg |

For anything you intend to model on, the vendor question is really a **point-in-time**
question. See `quant-data-pipeline`: a vendor that silently restates history will
manufacture alpha that does not exist.

### Technical indicators

`TA-Lib` when you need the canonical implementations and can install the C library,
`ta` or `finta` when you cannot, `talipp` or `streaming_indicators` when you need
incremental updates for live trading, and the `vectorbt` indicator factory when the
indicator will be swept over parameters. LEAN's own indicators when the code will run
in LEAN, because they handle warm-up and consolidation for you.

## 4. How to present a recommendation

State the choice, the reason it beat the alternative, and the cost you are accepting.
Three sentences is usually enough:

> Use `Riskfolio-Lib` for the allocator. It supports the CVaR objective and the
> sector constraints this mandate needs, which `PyPortfolioOpt` does not express
> directly. The cost is a heavier dependency and an API that is less obvious than the
> ML4T `allocation.py` helpers, so keep it behind a thin wrapper.

Do not present a list of six options with no verdict. That moves the decision back to
the person who asked.

## 5. Red flags in a candidate

- No tests and no CI.
- Last commit more than a year old with open issues about breakage.
- A README of screenshots and performance claims with no reproducible example.
- Backtest results in the README with no cost assumption stated.
- A "free tier" with no published limits.
- A trading bot promising a specific return.

The last one deserves emphasis. Several entries in the Trading & Backtesting category
are marketing rather than engineering. The list is curated for activity and format,
not for whether a strategy works.
