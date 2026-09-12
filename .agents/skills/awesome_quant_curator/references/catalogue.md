# Awesome-Quant Catalogue

Extracted from `awesome-quant/README.md`. Names are verbatim. Language tags are inline
in the source; entries below are grouped by the README's own category headings.

## Repository files

| Path | What it is |
|---|---|
| `README.md` | The list itself, 783 lines |
| `CONTRIBUTING.md` | Entry format, quality and commercial eligibility rules |
| `CLAUDE.md`, `AGENTS.md` | Agent-facing guidance for contributing and reviewing |
| `parse.py` | Parses the README, fetches commit dates and stars, writes `site/projects.csv` |
| `site/generate.py`, `site/index.html`, `site/projects.csv` | Static site generation |
| `scripts/readme_entries.py` | Shared entry parsing helpers |
| `scripts/validate_readme.py` | Entry validation, `--diff-from` mode for PRs |
| `scripts/review_pr.py` | Automated PR reviewer |
| `scripts/audit_readme.py`, `scripts/url_probe.py` | Link and repository audit |
| `scripts/migrate_readme.py` | The language-first to category-first migration |
| `cranscrape.py`, `cran.csv`, `topic.py` | CRAN and GitHub topic scrapers |
| `.claude/skills/`, `.agents/skills/` | `sprr`, `bprr`, `update-pypi-dates` |
| `.github/workflows/` | `build.yml` (daily site), `pr-validate.yml`, `pr-review.yml`, `readme-audit.yml` |

Entry format enforced by the parser regex: `^\s*- \[(.*)\]\((.*)\) - (.*)$`, with
backtick language tags, HTTPS-only URLs and a one-sentence description ending in a period.

## Numerical Libraries & Data Structures

`numpy`, `scipy`, `pandas`, `polars`, `quantdsl`, `statistics`, `sympy`, `pymc3`,
`modelx`, `ArcticDB`, `CRNG`, `jacobian`.

## Financial Instruments & Pricing

`PyQL`, `pyfin` (archived), `vollib`, `py_vollib`, `vanilla-option-pricers`,
`StochVolModels`, `QuantPy`, `Finance-Python`, `ffn`, `pynance`, `tia`, `pysabr`,
`FinancePy`, `gs-quant`, `willowtree`, `financial-engineering`, `optlib`,
`tf-quant-finance`, `Q-Fin`, `Quantsbin`, `finoptions`, `pypme`, `AbsBox`,
`mortgagemath`, `Intrinsic-Value-Calculator`, `Kelly-Criterion`, `rateslib`, `fypy`,
`Pyderivatives`, `quantra`, `optionlab`, `flashalpha`, `QuantOracle`, `BDE Score`,
`implied-expectations`, `QoX`.

## Technical Indicators

`pandas_talib`, `finta`, `Tulipy`, `lppls`, `talipp`, `streaming_indicators`,
`QuantWave`, `TA-Lib`, `ta`, `bta-lib`, `TuneTA`, `Wickra`.

## Trading & Backtesting

`lesson-book`, `cl-lp-rotation-scanner`, `midas-core`, `Manifold-BT`, `pyhood`,
`honest-signals`, `rulelint`, `FAIG`, `quantify`, `purgedcv`, `alpha-forge-mcp`,
`capitalcom-cli`, `DepthSight`, `Inalpha`, `income-desk`, `mx-trader-bridge`,
`AI Quant Agents`, `TradeSight`, `Orallexa`, `Vibe-Trading`, `DeepAlpha`, `the0`,
`autonomous-audit`, `Investing algorithm framework`, `Lumibot`, `QSTrader`, `Blankly`,
`zipline`, `zipline-reloaded`, `QuantSoftware Toolkit`, `quantitative`, `analyzer`,
`bt`, `backtrader`, `backtrader (cloudQuant fork)`, `TrendFollowingSystems`,
`backtest-bias`, `falsification-ledger`, `pyalgotrade`, `basana`, `algobroker`,
`finmarketpy`, `binary-martingale`, `zvt`, `pylivetrader`, `zipline-extensions`,
`moonshot`, `pyqstrat`, `NowTrade`, `pinkfish`, `PRISM-INSIGHT`, `FinClaw`,
`tw-stock-radar`, `aat`, `Backtesting.py`, `catalyst`, `quantstats`, `jquantstats`,
`qtpylib`, `Quantdom`, `freqtrade`, `algorithmic-trading-with-python`, `Qlib`,
`finlab`, `machine-learning-for-trading`, `AlphaPy`, `jesse`, `rqalpha`,
`FinRL-Library`, `aurumq-rl`, `bulbea`, `ib_nope`, `OctoBot`, `Stock-Prediction-Models`,
`AutoTrader`, `fast-trade`, `qf-lib`, `tda-api`, `vectorbt`, `Lean`, `pysystemtrade`,
`pytrendseries`, `PyLOB`, `PyBroker`, `OctoBot Script`, `hftbacktest`,
`orderflow-metrics`, `flashalpha-fill-simulator`, `vnpy`, `Intelligent Trading Bot`,
`fastquant`, `nautilus_trader`, `NoEdge-Bench`, `YABTE`, `Trading Strategy`, `Hikyuu`,
`rust_bt`, `Gunbot Quant`, `StrateQueue`, `PythonTradingFramework`,
`QTradeX-AI-Agents`, `QTradeX-Algo-Trading-SDK`, `antback`, `VARRD`,
`JIT-Optimization-Engine`, `backtester-mcp`, `ccxt`,
`binance-fix-connector-python`, `Sextant`, `ShowMe`, `TBV1`, `TraderHarness`,
`VerumTrade`, `mt5-httpapi`, `ibkr-httpapi`.

## Portfolio Optimization & Risk Analysis

`Multi-Axis Robust Portfolio Optimization`, `AutoHypothesis`, `skfolio`,
`PyPortfolioOpt`, `factorlasso`, `OptimalPortfolios`, `Eiten`, `riskparity.py`,
`mlfinlab`, `DeepDow`, `goal-based-allocation`, `QuantLibRisks`, `XAD`, `pyfolio`,
`etfray`, `empyrical`, `fecon235`, `finance`, `qfrm`, `visualize-wealth`,
`VisualPortfolio`, `universal-portfolios`, `FinQuant`, `Empyrial`, `risktools`,
`Riskfolio-Lib`, `empyrical-reloaded`, `pyfolio-reloaded`, `fincore`,
`fortitudo.tech`, `quantitative-finance-tools`, `Prop Trader Compass`, `riskkit`.

## Factor Analysis

`factor-qc`, `lookahead-free`, `Alpha Skills`, `alphalens`, `alphalens-reloaded`,
`Lacuna`, `Spectre`, `ml-quant-trading`, `QuantGPT`, `quant-lab-alpha`,
`Perception-XAlpha Lite`, `pit-release-gate`.

## Sentiment Analysis & Alternative Data

`Asset News Sentiment Analyzer`, `Social Stock Sentiment API`, `CoWorker Fin-Agent`,
`AlphaAI`, `StockKit` (TypeScript).

## Time Series Analysis

`ARCH`, `statsmodels`, `dynts`, `PyFlux`, `tsfresh`, `Facebook Prophet`, `tsmoothie`,
`pmdarima`, `gluon-ts`, `OmniOracle`, `functime`, `etf-pattern-match-pybind11`,
`wasserstein-btc`.

## Market Data & Data Sources

`ashare-data-immunity`, `pit-adjuster`, `perp-funding-collector`, `OpenBB Terminal`,
`Fincept Terminal`, `yfinance`, `coinpaprika-api-python-client`, `The Gold Barometer`,
`defeatbeta-api`, `financekit-mcp`, `dexpaprika-sdk-python`, `pricehub`, `Helium MCP`,
`findatapy`, `googlefinance`, `Horus Flow`, `yahoo-finance`, `pandas-datareader`,
`pandas-finance`, `pyhoofinance`, `yfinanceapi`, `yql-finance`, `ystockquote`,
`jugaad-data`, `nsetools`, `wallstreet`, `stock_extractor`, `Stockex`, `SwapAPI`,
`finsymbols`, `FRB`, `inquisitor`, `yfi`, `chinesestockapi`, `exchange`,
`unirate-api`, `Chart Library`, `ticks`, `pybbg`, `ccy`, `tushare`, `twmarketdata`,
`edinetdb`, `edinet-mcp`, `estat-mcp`, `tdnet-disclosure-mcp`, `bigtech-ai-stakes`,
`cn_stock_src`, `coinmarketcap`, `coinpulse`, `after-hours`, `bronto-python`, `pytdx`,
`pdblp`, `BloombergFetch`, `tiingo`, `finlight`, `iexfinance`, `pyEX`,
`alpaca-trade-api`, `metatrader5`, `akshare`, `yahooquery`, `investpy`, `yliveticker`,
`bbgbridge`, `polygon.io`, `SiftingIO`, `alpha_vantage`, `oilpriceapi`,
`FinanceDataReader`, `pystlouisfed`, `python-bcb`, `swiss-finance-data`,
`market-prices`, `tardis-python`, `lake-api`, `tessera-api`, `tessa`, `pandaSDMX`,
`cif`, `finagg`, `FinanceDatabase`, `FinanceToolkit`, `Trading Strategy`,
`datamule-python`, `fsynth`, `fedfred`, `edgar-sec`, `edgartools`,
`edgar-geo-revenue`, `filingrail-mcp`, `disclosure-alpha`, `Tradevo Data`,
`FilingFirehose`, `FXMacroData`, `uk-sic-codes`, `uk-company-number`, `veroq-python`,
`lse-data`, `Factor Weave`, `EarningsCall`, `AgentServices`.

## Prediction Markets

`pmxt`, `polymarket-whales`, `Polymarket Scanner API`, `PolyMind`,
`prediction-market-maker`, `Oracle3`, `marketlens`, `polymarket-bot-lab`, `polymm`,
`QuantRank500`, `outcometick`.

## Calendars & Market Hours

`exchange_calendars`, `bizdays`, `pandas_market_calendars`.

## Visualization

`D-Tale`, `mplfinance`, `finplot`, `finvizfinance`, `market-analy`, `QuantInvestStrats`.

## Excel & Spreadsheet Integration

`xlwings`, `openpyxl`, `xlrd`, `xlsxwriter`, `xlwt`, `xlloop`, `expy`, `pyxll`,
`Bilig` (TypeScript).

## Quant Research Environments

`QFO Quant Platform`, `Jupyter Quant`, `dsh-quant` (TypeScript).

## Non-Python sections

**R** — xts, data.table, sparseEigen, TSdbi, tseries, zoo, tis, tfplot, tframe,
RQuantLib, quantmod, Rmetrics (fAsianOptions, fAssets, fBasics, fBonds,
fExoticOptions, fOptions, fPortfolio), sde, YieldCurve, SmithWilsonYieldCurve,
ycinterextra, AmericanCallOpt, VarSwapPrice, RND, LSMonteCarlo, OptHedging, tvm,
OptionPricing, credule, derivmkts, FinCal, r-quant, options.studies, fmbasics,
R-fixedincome, TTR, backtest, pa, QuantTools, blotter, quantstrat, portfolio,
sparseIndexTracking, riskParityPortfolio, PortfolioAnalytics, PerformanceAnalytics,
covFactorModel, FactorAnalytics, Expected Returns, fGarch, timeSeries, rugarch,
rmgarch, tidypredict, tidyquant, timetk, tibbletime, matrixprofile, garchmodels,
IBrokers, Rblpapi, Rbitcoin, GetTDData, GetHFData, td, rbcb, rb3, simfinapi,
tidyfinance, timeDate, bizdays, direct_vola, Factor Weave.

**Matlab** — QUANTAXIS, PROJ_Option_Pricing_Matlab, RunMat.

**Julia** — Temporal.jl, DataFrames.jl, TSFrames.jl, TimeArrays.jl, QuantLib.jl,
Ito.jl, Miletus.jl, TALib.jl, Indicators.jl, TechnicalIndicatorCharts.jl,
MarketTechnicals.jl, OnlineTechnicalIndicators.jl, Fastback.jl, Lucky.jl, Planar.jl,
Strategems.jl, OnlinePortfolioAnalytics.jl, RiskPerf.jl, TimeSeries.jl, TimeFrames.jl,
CcyConv.jl, CryptoExchangeAPIs.jl, MarketData.jl, OnlineResamplers.jl,
LightweightCharts.jl.

**Java** — Strata, JQuantLib, finmath.net, quantcomponents, DRIP, ta4j,
ERN-WO Options Backtester, Wickra.

**JavaScript** — finance.js, IndicatorTS, orderflow, ccxt, portfolio-allocation,
Ghostfolio, rebalance, PENDAX, PreReason, pmxt, SimpleFunctions, outcometick,
QUANTAXIS_Webkit, dxcharts-lite, Exeria Charts, PineTS, The Stall, Wickra.

**TypeScript** — hagan-sabr, svi-vol-surface, compounded-sofr,
day-count-conventions, tips-index-ratio, 32nds, mkt-alerts, AlgoVault, DepthSight,
Inalpha, orderflow-metrics, TradeClaw, ShowMe, StockKit, treasurydirect,
treasury-fiscaldata, newyorkfed, commitments-of-traders, OpenChainBench, AlphaSMO,
SECfinAPI, finlight, Factor Weave, Backtesting Arena, sifma-holidays,
us-equity-market-calendar, fx-value-date, Bilig, dsh-quant, PineTS, Finterm.

**C++** — TradeFrame, OrderMatchingEngine, PandoraTrader, NexusFix,
Tolmachev Netcode SDK, Hikyuu, etf-pattern-match-pybind11, PineForge, godzilla.dev,
Wickra, Special-Relativity-in-Financial-Modeling.

**C#** — QuantConnect (Lean), StockSharp, TDAmeritrade.DotNetCore, QLNet.

**Rust** — QuantMath, RustQuant, QuantWave, TradeAggregation, SlidingFeatures,
fin-primitives, Manifold-BT, nautilus_trader, Barter, LFEST, ShowMe, Lacuna,
fin-stream, finalytics, Wickra, RunMat.

**Go** — IndicatorGo, Kelp, orderbook, OpenChainBench, Wickra.

**Haskell** — quantfin, Haxcel, Ffinar. **Scala** — QuantScale, Scala Quant.
**Ruby** — Jiji. **Elixir/Erlang** — Tai, Workbench, Prop.

**Cross-Language Frameworks** — RunMat, QuantLibRisks, XAD, QuantLib and its ports,
TA-Lib and its wrappers, godzilla.dev, PineTS.

**Reproducing Works, Training & Books** — Quant Sprint, QuantVault, Wyckoff Method
Course, Auto-Differentiation Website, Derman Papers, volatility-trading, quant,
fecon235, Quantitative-Notebooks, QuantEcon, FinanceHub, Python_Option_Pricing,
python-training, Stock_Analysis_For_Quant, algorithmic-trading-with-python,
MEDIUM_NoteBook, QuantFinance, IPythonScripts, Computational-Finance-Course,
Machine-Learning-for-Asset-Managers, Python-for-Finance-Cookbook,
modelos_vol_derivativos, NMOF, py4fi2nd, aiif, py4at, dawp, dx, QuantFinanceBook,
rough_bergomi, frh-fx, Value Investing Studies, Machine Learning Asset Management,
Deep Learning Machine Learning Stock, Technical Analysis and Feature Engineering,
Differential Machine Learning, systematictradingexamples, pysystemtrade_examples,
ML_Finance_Codes, cipher-starter, Hands-On Machine Learning for Algorithmic Trading,
financialnoob-misc, MesoSim Options Trading Strategy Library,
Quant-Finance-With-Python-Code, QuantFinanceTraining, book_irds3,
Autoencoder-Asset-Pricing-Models, Finance, 101_formulaic_alphas, Tidy Finance,
RoughVolatilityWorkshop, AFML, AlgoTradingLib, Portfolio Optimization Book,
direct_vola, TradeMux Snippets.

**Historical & Archived** — fooltrader, pipeline-live, pybacktest.

**Related Lists** — awesome-sec-filings, CONVEXFI.

## Broker, exchange and vendor index

**Broker and execution APIs**: Interactive Brokers (`IBrokers`, `ibkr-httpapi`,
`TradeFrame`), Alpaca (`alpaca-trade-api`, `pylivetrader`, `pipeline-live`),
TD Ameritrade (`tda-api`, `TDAmeritrade.DotNetCore`), Robinhood (`pyhood`),
Capital.com (`capitalcom-cli`), IG Index (`FAIG`), OANDA (`Jiji`), MetaTrader
(`metatrader5`, `mt5-httpapi`, `TradeMux`), Saxo Bank (`SaxoOpenAPI`), Korea
Investment KIS (`PRISM-INSIGHT`), Binance FIX
(`binance-fix-connector-python`), QuantRocket (`zipline-extensions`, `moonshot`),
multi-broker (`Lumibot`, `StrateQueue`, `Algorier`).

**Exchange and crypto venues**: `ccxt`, `pmxt`, `PENDAX`, `pricehub`,
`CryptoExchangeAPIs.jl`, `Planar.jl`, `tardis-python`, `lake-api`, `tessera-api`
(Hyperliquid), `0xArchive`, `pytdx`, `Rbitcoin`, `LFEST`, `FillBench`.

**Market-data vendors**: Bloomberg (`pybbg`, `pdblp`, `bbgbridge`, `BloombergFetch`,
`Rblpapi`), Yahoo (`yfinance`, `yahooquery`, `yliveticker`, and others), IEX
(`iexfinance`, `pyEX`), Polygon, Alpha Vantage, Tiingo, Twelve Data (`td`), Nasdaq
Data Link, SimFin (`simfinapi`), `SiftingIO`, `lse-data`, `Factor Weave`,
`veroq-python`, `Helium MCP`, `AgentServices`.

**Official sources**: SEC EDGAR (`edgartools`, `edgar-sec`, `datamule-python`,
`filingrail-mcp`, `disclosure-alpha`, `FilingFirehose`, `SECfinAPI`), NSE and BSE
(`jugaad-data`, `nsetools`), Brazil B3 (`rb3`, `GetTDData`, `GetHFData`, `rbcb`,
`python-bcb`), Japan (`edinetdb`, `edinet-mcp`, `tdnet-disclosure-mcp`, `estat-mcp`),
Korea (`FinanceDataReader`), China (`tushare`, `akshare`, `cn_stock_src`),
Taiwan (`twmarketdata`, `finlab`), US Treasury, Fed and CFTC (`pystlouisfed`,
`fedfred`, `FRB`, `treasurydirect`, `treasury-fiscaldata`, `newyorkfed`,
`commitments-of-traders`), SNB (`swiss-finance-data`), SDMX (`pandaSDMX`).

## Contribution and maintenance model

PRs only, one project per PR preferred. Active projects need commits within twelve
months and a README with usage examples. Archived projects qualify only under the
narrow Historical rules. Repository-less commercial services need a permanent free
tier, published pricing and limits, public documentation, non-promotional wording and
tracking-free URLs, and belong in **Commercial & Proprietary Services**.

Four GitHub Actions: `Validate PR` and `PR Review` must both pass on the latest
revision, `README Audit` runs link and repository audits, and `Update site` runs daily
at `0 1 * * *`, executing `parse.py` then `site/generate.py` and deploying to Pages.

Automatic rejection: unrelated multi-project PRs, format mismatches, duplicates
including recently closed PRs, archived or abandoned projects outside the Historical
criteria, and empty PR descriptions.
