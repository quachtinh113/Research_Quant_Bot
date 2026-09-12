---
name: awesome-quant-curator
description: Choose the right quant library, data vendor, broker API or exchange connector from the awesome-quant index, with selection criteria and licence and maintenance caveats.
---

# Awesome-Quant Library & Vendor Curator

`awesome-quant` is the discovery layer of this suite: 699 curated entries covering
libraries, data vendors, broker APIs and exchange connectors across a dozen languages.
Use it to answer "what should I use for X" with a real, maintained option rather than
whatever comes to mind first.

Repository: `awesome-quant/`.

## Read the structure correctly

The list is **no longer organised by language**. It was migrated to a **category-first**
structure with inline backtick language tags on each entry. There is no `## Python`
section with subsections. The categories you might remember as Python subsections are
now top-level headings, and each entry carries tags such as `` `Python` ``,
`` `Rust` ``, `` `MCP` ``.

Of the 699 entries, 381 carry a Python tag.

The twenty top-level categories, in order:

1. Contents
2. Numerical Libraries & Data Structures
3. Financial Instruments & Pricing
4. Technical Indicators
5. Trading & Backtesting
6. Portfolio Optimization & Risk Analysis
7. Factor Analysis
8. Sentiment Analysis & Alternative Data
9. Time Series Analysis
10. Market Data & Data Sources
11. Prediction Markets
12. Calendars & Market Hours
13. Visualization
14. Excel & Spreadsheet Integration
15. Quant Research Environments
16. Cross-Language Frameworks
17. Reproducing Works, Training & Books
18. Commercial & Proprietary Services
19. Historical & Archived Projects
20. Related Lists

## How to use it well

**Do not just name the most popular package.** The list exists because the popular
answer is often wrong for the specific job. Before recommending anything, establish:

1. **The asset class and frequency.** A daily equity cross-section, a crypto perpetual
   funding strategy and a limit-order-book study need different tools.
2. **Whether the licence permits the intended use.** Several highly rated entries are
   Apache with a Commons Clause, AGPL, or a free tier with published limits.
3. **Whether it is maintained.** The repository's own quality gate is commits within
   twelve months and a README with usage examples. Entries in the
   **Historical & Archived Projects** section fail that gate deliberately.
4. **Whether it duplicates something already in this suite.** If Qlib, vectorbt or LEAN
   already covers the need, adding a fourth backtester is a cost, not a capability.

## The short list this suite actually depends on

When someone asks "what should I use", these are the defaults, and the awesome-quant
index is where you go when the default does not fit.

| Job | Default here | Reach for the index when |
|---|---|---|
| Vectorised prototyping | `vectorbt` | you need event-driven fills or an order book |
| Event-driven backtest and live | `Lean` | you need a pure-Python engine or a niche broker |
| Cross-sectional alpha | `qlib` | you need a different factor library or a research environment |
| Portfolio optimisation | ML4T `case_studies/utils/allocation.py` | you need CVaR, entropy pooling or robust shrinkage: see `Riskfolio-Lib`, `skfolio`, `PyPortfolioOpt`, `fortitudo.tech` |
| Tear sheets | MindsHub reporting | you want `quantstats`, `pyfolio-reloaded`, `empyrical-reloaded` |
| Factor evaluation | ML4T `05_evaluation` stage | you want `alphalens-reloaded`, `Spectre` (GPU) |
| Market data | ML4T `data/` loaders | you need a vendor: see the Market Data category |
| Technical indicators | `vectorbt` factory, LEAN indicators | you want `TA-Lib`, `ta`, `finta`, `talipp` (incremental), `Tulipy` |

## Categories most worth knowing by name

**Numerical**: `numpy`, `scipy`, `pandas`, `polars`, `ArcticDB` (tick datastore),
`statistics`, `sympy`, `pymc3`, `modelx`, `quantdsl`.

**Pricing**: `QuantLib` and its ports (`PyQL`, `QLNet`, `RQuantLib`, `QuantLib.jl`),
`FinancePy`, `gs-quant`, `tf-quant-finance`, `rateslib` (fixed income), `py_vollib`,
`vollib`, `StochVolModels`, `pysabr`, `optionlab`, `fypy`, `Q-Fin`.

**Indicators**: `TA-Lib`, `ta`, `finta`, `pandas_talib`, `Tulipy`, `talipp`,
`streaming_indicators`, `bta-lib`, `TuneTA`, `lppls`.

**Trading & backtesting**: `zipline-reloaded`, `backtrader`, `bt`, `Backtesting.py`,
`QSTrader`, `pyalgotrade`, `pyqstrat`, `nautilus_trader` (Rust core),
`hftbacktest` (queue position and latency), `vnpy`, `freqtrade`, `jesse`, `OctoBot`,
`Lumibot`, `Blankly`, `AutoTrader`, `PyBroker`, `pysystemtrade`, `qf-lib`,
`fastquant`, `Trading Strategy` (DeFi), `Hikyuu` (C++), `purgedcv` (purged and
combinatorial CV with PBO and DSR).

**Portfolio & risk**: `Riskfolio-Lib`, `skfolio`, `PyPortfolioOpt`, `riskparity.py`,
`mlfinlab`, `DeepDow`, `pyfolio-reloaded`, `empyrical-reloaded`, `quantstats`,
`FinQuant`, `Empyrial`, `fortitudo.tech` (CVaR and entropy pooling),
`universal-portfolios`, `fincore`, `XAD` and `QuantLibRisks` (adjoint algorithmic
differentiation).

**Factor analysis**: `alphalens-reloaded`, `Spectre` (GPU factor engine),
`factor-qc` (fail-closed DSR/PBO/haircut gate), `lookahead-free`, `Lacuna` (Rust
leakage and point-in-time validation), `Perception-XAlpha Lite` (CSCV PBO, deflated
Sharpe, White's Reality Check), `pit-release-gate`.

**Time series**: `statsmodels`, `ARCH`, `PyFlux`, `tsfresh`, `Prophet`, `pmdarima`,
`gluon-ts`, `tsmoothie`, `functime` (Polars-native at scale).

**Market data**: `yfinance`, `yahooquery`, `polygon.io`, `alpha_vantage`, `tiingo`,
`iexfinance`, `pyEX`, `akshare`, `tushare`, `FinanceDataReader`, `pandas-datareader`,
`findatapy`, `OpenBB Terminal`, `edgartools` and `datamule-python` (SEC EDGAR),
`fedfred` and `pystlouisfed` (FRED), `tardis-python` and `lake-api` (crypto tick),
`exchange_calendars` and `pandas_market_calendars` (trading calendars),
`pdblp` and `pybbg` (Bloomberg).

**Broker and exchange APIs**: `ccxt` (100+ crypto venues), `alpaca-trade-api`,
`tda-api`, `IBrokers` and `ibkr-httpapi` (Interactive Brokers), `metatrader5` and
`mt5-httpapi`, `capitalcom-cli`, `binance-fix-connector-python`, `pmxt`
(prediction markets, "the CCXT for Polymarket and Kalshi").

**Research environments**: `Jupyter Quant` (dockerised: statsmodels, pymc, arch,
py_vollib, zipline-reloaded, PyPortfolioOpt), `QFO Quant Platform`.

## Licensing caveat

There is **no LICENSE file** in this checkout and the README makes no licence
statement. The licence mentions inside it refer to the listed projects, not to the
list. Project metadata names Wilson Freitas as author; the canonical site is
`https://wilsonfreitas.github.io/awesome-quant/`. Treat the list's own licensing as
unspecified, and always check each recommended project's own licence separately.

## References

- Full extracted inventory by category: [catalogue.md](references/catalogue.md)
- How to choose between candidates: [selection-guide.md](references/selection-guide.md)
- Auto-generated repository map: [project-structure.md](references/project-structure.md)
- Auto-generated dependency map: [tech-stacks.md](references/tech-stacks.md)

## Related skills

`quant-data-pipeline` when the question is about a data vendor rather than a library,
`portfolio-construction-risk` when comparing optimisers, `backtest-risk-audit` when
comparing validation tools.
