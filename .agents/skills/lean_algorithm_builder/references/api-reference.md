# QuantConnect LEAN API Reference

Verified against the sparse checkout in `Lean/`. C# signatures are given because they
are the source of truth; the Python name is the snake_case form of the same member.

## 0. What is present and what is missing

Present: `Algorithm/`, `Algorithm.Framework/`, `Algorithm.Python/` (429 files),
`Common/`, `Indicators/` (169 files), `Engine/`, `Report/`, `Optimizer/`, `Api/`,
`Configuration/`, `Launcher/`.

Absent from this checkout: `Data/`, `Tests/`, `Research/`, `Brokerages/` (the
top-level brokerage implementations project), `ToolBox/`, `Queues/`, `Messaging/`,
`Logging/`, `AlgorithmFactory/`, `Algorithm.CSharp/`, `DataSource/`. The solution
cannot be built and no backtest can be run from this checkout alone.

## 1. QCAlgorithm

`public partial class QCAlgorithm : MarshalByRefObject, IAlgorithm`, split across
`Algorithm/QCAlgorithm.cs` plus `.Trading.cs`, `.History.cs`, `.Indicators.cs`,
`.Universe.cs`, `.Framework.cs`, `.Plotting.cs`, `.Python.cs`, `.Framework.Python.cs`.

### Lifecycle

| C# | Python | Location |
|---|---|---|
| `virtual void Initialize()` | `initialize(self)` | `QCAlgorithm.cs:770` |
| `virtual void OnData(Slice slice)` | `on_data(self, slice)` | `:1079` |
| `virtual void OnSecuritiesChanged(SecurityChanges changes)` | `on_securities_changed` | `:1152` |
| `virtual void OnOrderEvent(OrderEvent orderEvent)` | `on_order_event` | `:1229` |

### Setup

| Member | Location |
|---|---|
| `SetStartDate(int year, int month, int day)` | `:1690` |
| `SetEndDate(int year, int month, int day)` | `:1716` |
| `SetCash(decimal startingCash)` | `:1648` |
| `SetAccountCurrency(string accountCurrency, decimal? startingCash = null)` | `:1599` |
| `SetTimeZone(string \| DateTimeZone)` | `:1295`, `:1315` |
| `SetBrokerageModel(BrokerageName brokerage, AccountType accountType = AccountType.Margin)` | `:1353` |
| `SetBenchmark(Symbol)` / `(string ticker)` / `(SecurityType, string)` / `(Func<DateTime,decimal>)` | `:1503`, `:1474`, `:1450`, `:1522` |
| `SetSecurityInitializer(ISecurityInitializer \| Action<Security,bool> \| Action<Security>)` | `:964`, `:990`, `:1002` |
| `Debug(string)` / `Log(string)` / `Error(string)` | `:2806`, `:2856`, `:2905` |
| `Train(Action)` / `Train(IDateRule, ITimeRule, Action)` | `:3121`, `:3134` |

### Subscriptions

| Member | Location |
|---|---|
| `AddEquity(string ticker, Resolution? resolution = null, string market = null, bool fillForward = true, …)` | `:2120` |
| `AddOption(string underlying, Resolution?, string market, bool? fillForward, decimal leverage)` | `:2136` |
| `AddOptionContract(Symbol, …)` | `:2411` |
| `AddFuture(string ticker, Resolution?, string market, …)` | `:2219` |
| `AddFutureContract(Symbol, …)` | `:2248` |
| `AddForex(...)` | `:2507` |
| `AddCrypto(...)` | `:2553` |

### Scheduling — `Common/Scheduling/ScheduleManager.cs`

`Schedule` property at `QCAlgorithm.cs:401`; `DateRules` at `:453`, `TimeRules` at `:462`.
`On(IDateRule, ITimeRule, Action)` `:132`, `On(IDateRule, ITimeRule, PyObject)` `:143`,
named variants `:167`, `:179`, `:191`. Rules defined in `DateRules.cs` and `TimeRules.cs`.

### Warm-up and history — `Algorithm/QCAlgorithm.History.cs`

`SetWarmUp(TimeSpan)` `:77`, `(TimeSpan, Resolution?)` `:99`, `(int barCount)` `:125`,
`(int barCount, Resolution?)` `:149`.

About twenty `History` overloads, including
`IEnumerable<TradeBar> History(Symbol symbol, int periods, Resolution? resolution = null, …)` `:489`,
`IEnumerable<Slice> History(IEnumerable<Symbol>, DateTime start, DateTime end, …)` `:680`,
generic `IEnumerable<T> History<T>(Symbol, TimeSpan span, …)` `:465`,
`History(Universe universe, int periods, …)` `:288`. In Python these return a pandas
DataFrame through `Common/PandasMapper.py` unless a C#-typed overload is forced.

### Trading — `Algorithm/QCAlgorithm.Trading.cs`

| Member | Location |
|---|---|
| `SetHoldings(Symbol, decimal percentage, bool liquidateExistingHoldings = false, bool asynchronous = false, string tag = null, IOrderProperties = null)` | `:1547` |
| `SetHoldings` double/float/int/`List<PortfolioTarget>` overloads | `:1460`–`:1527` |
| `MarketOrder(Symbol, decimal quantity, bool asynchronous = false, string tag = "", IOrderProperties = null)` | `:241` |
| `LimitOrder(Symbol, decimal quantity, decimal limitPrice, …)` | `:473` |
| `StopMarketOrder(Symbol, decimal quantity, decimal stopPrice, …)` | `:525` |
| `StopLimitOrder(Symbol, decimal, decimal stopPrice, decimal limitPrice, …)` | `:711` |
| `MarketOnOpenOrder` / `MarketOnCloseOrder` | `:337`, `:388` |
| `Liquidate(Symbol = null, bool asynchronous = false, string tag = null, …)` | `:1325` |
| `Liquidate(IEnumerable<Symbol>, …)` | `:1348` |
| `CalculateOrderQuantity(Symbol, decimal target)` | `:1635` |

### Framework wiring — `Algorithm/QCAlgorithm.Framework.cs`

`SetUniverseSelection` `:271`, `AddUniverseSelection` `:282`, `SetAlpha` `:307`,
`AddAlpha` `:317`, `SetPortfolioConstruction` `:343`, `SetExecution` `:354`,
`SetRiskManagement` `:365`, `AddRiskManagement` `:376`, `EmitInsights(params Insight[])` `:403`.

## 2. The five framework models

All models also implement `INotifiedSecurityChanges.OnSecuritiesChanged(QCAlgorithm, SecurityChanges)`
(`Algorithm/INotifiedSecurityChanges.cs`).

### Universe selection

Interface `IUniverseSelectionModel` (`Algorithm/Selection/IUniverseSelectionModel.cs`):
`IEnumerable<Universe> CreateUniverses(QCAlgorithm)`, `DateTime GetNextRefreshTimeUtc()`.
Base `UniverseSelectionModel` (`Algorithm/Selection/UniverseSelectionModel.cs:40,50`).

Built-ins: `ManualUniverseSelectionModel`, `CustomUniverseSelectionModel`,
`CompositeUniverseSelectionModel`, `OptionChainedUniverseSelectionModel`
(all `Algorithm/Selection/`); `FundamentalUniverseSelectionModel`,
`QC500UniverseSelectionModel`, `ETFConstituentsUniverseSelectionModel`,
`ScheduledUniverseSelectionModel`, `EmaCrossUniverseSelectionModel`,
`FutureUniverseSelectionModel`, `OptionUniverseSelectionModel`, `LiquidETFUniverse`
(all `Algorithm.Framework/Selection/`).

### Alpha

Interface `IAlphaModel` (`Algorithm/Alphas/IAlphaModel.cs`):
`IEnumerable<Insight> Update(QCAlgorithm algorithm, Slice data)`.
Base `AlphaModel` (`Algorithm/Alphas/AlphaModel.cs:49`, `Name` at `:32`);
also `CompositeAlphaModel`, `NullAlphaModel`.

Built-ins (`Algorithm.Framework/Alphas/`): `ConstantAlphaModel`, `EmaCrossAlphaModel`,
`MacdAlphaModel`, `RsiAlphaModel`, `HistoricalReturnsAlphaModel`,
`BasePairsTradingAlphaModel`, `PearsonCorrelationPairsTradingAlphaModel`.

### Portfolio construction

Interface `IPortfolioConstructionModel`
(`Algorithm/Portfolio/IPortfolioConstructionModel.cs`):
`IEnumerable<IPortfolioTarget> CreateTargets(QCAlgorithm algorithm, Insight[] insights)`.
Base `PortfolioConstructionModel` (`Algorithm/Portfolio/PortfolioConstructionModel.cs`):
override `CreateTargets` `:93` or, more usually,
`protected virtual Dictionary<Insight,double> DetermineTargetPercent(List<Insight> activeInsights)` `:195`.
Also `ShouldCreateTargetForInsight` `:185`, `IsRebalanceDue` `:248`,
`RebalanceOnSecurityChanges` `:39`, `RebalanceOnInsightChanges` `:44`.

Built-ins (`Algorithm.Framework/Portfolio/`): `EqualWeightingPortfolioConstructionModel`,
`InsightWeightingPortfolioConstructionModel`, `ConfidenceWeightedPortfolioConstructionModel`,
`MeanVarianceOptimizationPortfolioConstructionModel`,
`BlackLittermanOptimizationPortfolioConstructionModel`,
`RiskParityPortfolioConstructionModel`, `SectorWeightingPortfolioConstructionModel`,
`AccumulativeInsightPortfolioConstructionModel`, `MeanReversionPortfolioConstructionModel`.

Optimisers implementing `IPortfolioOptimizer`: `MaximumSharpeRatioPortfolioOptimizer`,
`MinimumVariancePortfolioOptimizer`, `RiskParityPortfolioOptimizer`,
`UnconstrainedMeanVariancePortfolioOptimizer`.

### Execution

Interface `IExecutionModel` (`Algorithm/Execution/IExecutionModel.cs`):
`void Execute(QCAlgorithm algorithm, IPortfolioTarget[] targets)` and
`void OnOrderEvent(QCAlgorithm, OrderEvent)`. Base `ExecutionModel` `:49`.

Built-ins: `ImmediateExecutionModel`, `NullExecutionModel` (`Algorithm/Execution/`);
`VolumeWeightedAveragePriceExecutionModel`, `StandardDeviationExecutionModel`,
`SpreadExecutionModel` (`Algorithm.Framework/Execution/`).

### Risk management

Interface `IRiskManagementModel` (`Algorithm/Risk/IRiskManagementModel.cs`):
`IEnumerable<IPortfolioTarget> ManageRisk(QCAlgorithm algorithm, IPortfolioTarget[] targets)`.
Base `RiskManagementModel` `:32`; `CompositeRiskManagementModel`.

Built-ins (`Algorithm.Framework/Risk/`): `MaximumDrawdownPercentPerSecurity`,
`MaximumDrawdownPercentPortfolio`, `MaximumUnrealizedProfitPercentPerSecurity`,
`TrailingStopRiskManagementModel`, `MaximumSectorExposureRiskManagementModel`.

## 3. Insight — `Common/Algorithm/Framework/Alphas/Insight.cs`

Properties: `Symbol` `:71`, `Type` `:76`, `Direction` `:91`, `Magnitude` (`double?`) `:101`,
`Confidence` (`double?`) `:106`, `Weight` (`double?`) `:111`, `Score` `:116`,
`SourceModel` `:49`.

Constructors at `:178`, `:195`, `:223`, `:240`, `:260`, e.g.
`Insight(Symbol, TimeSpan period, InsightType, InsightDirection, double? magnitude, double? confidence, string sourceModel = null, double? weight = null, string tag = "")`.

Factories `Insight.Price(...)` at `:352`, `:375`, `:394`, `:418`:

```text
Insight.Price(Symbol symbol, TimeSpan period, InsightDirection direction,
              double? magnitude = null, double? confidence = null,
              string sourceModel = null, double? weight = null, string tag = "")
Insight.Price(Symbol, Resolution resolution, int barCount, InsightDirection, …)
Insight.Price(Symbol, DateTime closeTimeLocal, InsightDirection, …)
Insight.Price(Symbol, Func<DateTime,DateTime> expiryFunc, InsightDirection, …)
```

`InsightDirection`: `Down = -1`, `Flat = 0`, `Up = 1` (Python `DOWN`, `FLAT`, `UP`).
`InsightType`: `Price`, `Volatility` (Python `PRICE`, `VOLATILITY`).

## 4. Indicators

Helper factories on `Algorithm/QCAlgorithm.Indicators.cs` construct **and register**
the indicator:

| Helper | Location |
|---|---|
| `SMA(Symbol, int period, Resolution? = null, Func<IBaseData,decimal> selector = null)` | `:2195` |
| `EMA(...)` | `:811` |
| `RSI(Symbol, int period, MovingAverageType = Wilders, …)` | `:1959` |
| `MACD(Symbol, int fast, int slow, int signal, MovingAverageType = Exponential, …)` | `:1398` |
| `BB(Symbol, int period, decimal k, …)` | `:402` |
| `ATR(Symbol, int period, MovingAverageType = Simple, …)` | `:363` |

Manual wiring: `RegisterIndicator(Symbol, IndicatorBase<IndicatorDataPoint>, Resolution?|TimeSpan?|IDataConsolidator, selector)` `:3214`, `:3229`, `:3244`;
generic `RegisterIndicator<T>` `:3268`–`:3316`.
Warm-up: `WarmUpIndicator(Symbol|IEnumerable<Symbol>, indicator, Resolution?|TimeSpan, selector)` `:3386`–`:3517`.
History of indicator values: `IndicatorHistory(indicator, symbol, int period|TimeSpan|DateTime start/end, Resolution?, selector)` `:3927`–`:4081`.
Consolidator resolution: `ResolveConsolidator(Symbol, Resolution?|TimeSpan?, Type dataType = null)` `:3676`.

Consolidators (`Common/Data/Consolidators/`): `TradeBarConsolidator`,
`QuoteBarConsolidator`, `TickConsolidator`, `TickQuoteBarConsolidator`,
`BaseDataConsolidator`, `RenkoConsolidator`, `ClassicRenkoConsolidator`,
`VolumeRenkoConsolidator`, `DollarVolumeRenkoConsolidator`, `RangeConsolidator`,
`ClassicRangeConsolidator`, `SequentialConsolidator`, `IdentityDataConsolidator`,
`FilteredIdentityDataConsolidator`, `MarketHourAwareConsolidator`,
`SessionConsolidator`, `OpenInterestConsolidator`, `DynamicDataConsolidator`.

Common indicator classes (`Indicators/<Name>.cs`): `SimpleMovingAverage`,
`ExponentialMovingAverage`, `RelativeStrengthIndex`,
`MovingAverageConvergenceDivergence`, `BollingerBands`, `AverageTrueRange`,
`StandardDeviation`, `Variance`, `Stochastic`, `CommodityChannelIndex`,
`MoneyFlowIndex`, `OnBalanceVolume`, `AverageDirectionalIndex`, `Momentum`,
`RateOfChange`, `VolumeWeightedAveragePriceIndicator`, `IchimokuKinkoHyo`,
`ParabolicStopAndReverse`, `KeltnerChannels`, `DonchianChannel`, `WilliamsPercentR`,
`Beta`, `Correlation`, `LogReturn`, `SuperTrend`, `Trix`, `UltimateOscillator`,
`ChandeMomentumOscillator`. Candlestick patterns live under
`Indicators/CandlestickPatterns/`, exposed by `Algorithm/CandlestickPatterns.cs`.

## 5. Data model — `Common/Data`

`Slice.cs`: `Time` `:62`, `Bars` `:86`, `QuoteBars` `:94`, `Ticks` `:102`,
`OptionChains` `:110`, `FuturesChains` `:118`, `Splits` `:134`, `Dividends` `:142`,
`Delistings` `:150`, `SymbolChangedEvents` `:158`, `MarginInterestRates` `:166`,
`DataDictionary<T> Get<T>()` `:358`, `T Get<T>(Symbol)` `:517`, plus `slice[symbol]`.

Market types (`Common/Data/Market/`): `TradeBar`, `QuoteBar`, `Tick`, `Bar`,
`RenkoBar`, `RangeBar`, `OptionChain(s)`, `OptionContract`, `FuturesChain(s)`,
`Greeks`, `Dividend`, `Split`, `Delisting`, `OpenInterest`, `DataDictionary`.

Custom data: subclass `BaseData` (`Common/Data/BaseData.cs`) or `DynamicData` and
override
`virtual SubscriptionDataSource GetSource(SubscriptionDataConfig config, DateTime date, bool isLiveMode)` `:179`
and
`virtual BaseData Reader(SubscriptionDataConfig config, string line, DateTime date, bool isLiveMode)` `:148`
(stream overload `:167`). Optional: `RequiresMapping()` `:209`, `IsSparseData()` `:221`,
`DefaultResolution()` `:241`, `EndTime` `:96`, `Value` `:113`. Register with `AddData<T>`.

Enums in `Common/Global.cs`: `Resolution` `:582` = `Tick, Second, Minute, Hour, Daily`;
`SecurityType` `:352` = `Base, Equity, Option, Commodity, Forex, Future, Cfd, Crypto,
FutureOption, Index, …`; `TickType` `:528`; `MarketDataType` `:444`; `OptionRight` `:634`;
`OptionStyle` `:650`; `DataNormalizationMode` `:924`; `DataMappingMode` `:966`;
`AccountType` `:428`; `AlgorithmMode` `:1262`.

`Common/Market.cs` constants: `USA`, `Oanda`, `FXCM`, `Dukascopy`, `Bitfinex`,
`Globex` (`"cmeglobex"`), `NYMEX`, `CBOT`, `ICE`, `CBOE`, `CFE`, `COMEX`, `CME`,
`EUREX`, `SGX`, `HKFE`, `OSE`, `NYSELIFFE`, `India`, `Coinbase` (aliased by `GDAX`),
`Kraken`, `Binance`, `BinanceUS`, `Bybit`, `Bitstamp`, `KRX`, `InteractiveBrokers`, `DYDX`.

## 6. Universe selection API — `Algorithm/QCAlgorithm.Universe.cs`

| Form | Location |
|---|---|
| `AddUniverse(Func<IEnumerable<Fundamental>, IEnumerable<Symbol>> selector)` | `:435` |
| `AddUniverse(IDateRule dateRule, Func<IEnumerable<Fundamental>, IEnumerable<Symbol>>)` | `:447` |
| `AddUniverse(coarseSelector, fineSelector)` (legacy two-stage) | `:462` |
| `AddUniverse(Universe universe, Func<IEnumerable<Fundamental>, IEnumerable<Symbol>> fineSelector)` | `:482` |
| `AddUniverse<T>(string name, Resolution, UniverseSettings, Func<IEnumerable<BaseData>, IEnumerable<Symbol>>)` | `:345` (siblings `:228`–`:423`) |
| `AddUniverse(string name, Func<DateTime, IEnumerable<string>> selector)` | `:494`, `:507`, `:522` |

ETF constituents: `ETFConstituentUniverse`
(`Common/Data/UniverseSelection/ETFConstituentUniverse.cs`) and
`ETFConstituentsUniverseSelectionModel` (six constructor overloads, `:39`–`:110`).

`ScheduledUniverseSelectionModel(IDateRule, ITimeRule, Func<DateTime, IEnumerable<Symbol>>, UniverseSettings = null)` `:45`,
plus timezone and `PyObject` overloads `:61`, `:77`, `:90`.

`FundamentalUniverseSelectionModel` overrides: `CreateUniverses` `:145`,
`CreateCoarseFundamentalUniverse` `:176`,
`virtual IEnumerable<Symbol> Select(QCAlgorithm, IEnumerable<Fundamental>)` `:205`.

Supporting types: `Common/Data/UniverseSelection/Universe.cs`, `UniverseSettings.cs`,
`SecurityChanges.cs`, `ScheduledUniverse.cs`, `CoarseFundamental.cs`,
`OptionUniverse.cs`, `FutureUniverse.cs`.

## 7. Reality modelling

**Fees** (`Common/Orders/Fees/`) — `IFeeModel`, base `FeeModel`, `OrderFee`,
`OrderFeeParameters`. Implementations include `ConstantFeeModel`,
`InteractiveBrokersFeeModel`, `AlpacaFeeModel`, `BinanceFeeModel`,
`BinanceFuturesFeeModel`, `BinanceCoinFuturesFeeModel`, `BitfinexFeeModel`,
`BybitFeeModel`, `BybitFuturesFeeModel`, `CoinbaseFeeModel`, `GDAXFeeModel`,
`KrakenFeeModel`, `FxcmFeeModel`, `FTXFeeModel`, `FTXUSFeeModel`, `ExanteFeeModel`,
`IndiaFeeModel`, `ZerodhaFeeModel`, `SamcoFeeModel`, `RBIFeeModel`,
`TDAmeritradeFeeModel`, `TradeStationFeeModel`, `CharlesSchwabFeeModel`,
`TastytradeFeeModel`, `WebullFeeModel`, `WolverineFeeModel`, `AxosFeeModel`,
`EzeFeeModel`, `AlphaStreamsFeeModel`, `PublicFeeModel`, `dYdXFeeModel`.

**Slippage** (`Common/Orders/Slippage/`) — `ISlippageModel`; `ConstantSlippageModel`,
`VolumeShareSlippageModel`, `MarketImpactSlippageModel`, `AlphaStreamsSlippageModel`,
`NullSlippageModel`.

**Fills** (`Common/Orders/Fills/`) — `IFillModel`, base `FillModel`,
`FillModelParameters`, `Fill`, `Prices`; `ImmediateFillModel`, `EquityFillModel`,
`FutureFillModel`, `FutureOptionFillModel`, `LatestPriceFillModel`.

**Brokerage models** (`Common/Brokerages/`) — `IBrokerageModel`,
`DefaultBrokerageModel`, and roughly forty-five concretes including
`InteractiveBrokersBrokerageModel`, `InteractiveBrokersFixModel`,
`TradierBrokerageModel`, `OandaBrokerageModel`, `FxcmBrokerageModel`,
`AlpacaBrokerageModel`, `BinanceBrokerageModel` (plus Futures, CoinFutures, US),
`BitfinexBrokerageModel`, `CoinbaseBrokerageModel`, `GDAXBrokerageModel`,
`KrakenBrokerageModel`, `BybitBrokerageModel`, `TradeStationBrokerageModel`,
`CharlesSchwabBrokerageModel`, `TastytradeBrokerageModel`, `ZerodhaBrokerageModel`,
`SamcoBrokerageModel`, `ExanteBrokerageModel`, `TradingTechnologiesBrokerageModel`,
`TerminalLinkBrokerageModel`, `AlphaStreamsBrokerageModel`, `dYdXBrokerageModel`.

`BrokerageName` enum (`Common/Brokerages/BrokerageName.cs`): `Default`,
`InteractiveBrokersBrokerage`, `TradierBrokerage`, `OandaBrokerage`, `FxcmBrokerage`,
`Bitfinex`, `Binance`, `GDAX = 12`, `Alpaca`, `AlphaStreams`, `Zerodha`, `Samco`,
`Atreyu`, `TradingTechnologies`, `Kraken`, `FTX`, `FTXUS`, `Exante`, `BinanceUS`,
`Wolverine`, `TDAmeritrade`, `BinanceFutures`, `BinanceCoinFutures`, `RBI`, `Bybit`,
`Eze`, `Axos`, `Coinbase`, `TradeStation`, `TerminalLink`, `CharlesSchwab`,
`Tastytrade`, `InteractiveBrokersFix`, `DYDX`, `Webull`, `Public`, `BloombergFix`,
`ClearStreet`.

## 8. Engine pipeline

`Launcher/Program.cs::Main` → `Initializer.Start()` → `Initializer.GetSystemHandlers()`
(`LeanEngineSystemHandlers`: `JobQueue`, `Api`, `Notify`, `LeanManager`) →
`JobQueue.NextJob(out assemblyPath)` → `Initializer.GetAlgorithmHandlers()`
(`LeanEngineAlgorithmHandlers`) → `Engine.Run(job, algorithmManager, assemblyPath, workerThread)`
→ `AlgorithmManager.Run(...)`.

| Interface | Implementations |
|---|---|
| `Engine/Setup/ISetupHandler.cs` | `BacktestingSetupHandler`, `BrokerageSetupHandler`, `ConsoleSetupHandler`, `BaseSetupHandler` |
| `Engine/DataFeeds/IDataFeed.cs` | `FileSystemDataFeed`, `LiveTradingDataFeed`; plus `DataManager`, `SubscriptionManager`, `AggregationManager`, `DefaultDataProvider`, `ApiDataProvider`, `DownloaderDataProvider` |
| `Engine/TransactionHandlers/ITransactionHandler.cs` | `BacktestingTransactionHandler`, `BrokerageTransactionHandler` |
| `Engine/Results/IResultHandler.cs` | `BacktestingResultHandler`, `LiveTradingResultHandler`, `RegressionResultHandler`, base `BaseResultsHandler` |
| `Engine/RealTime/IRealTimeHandler.cs` | `BacktestingRealTimeHandler`, `LiveTradingRealTimeHandler` |

Also `Engine/HistoricalData/` history providers and `Engine/Storage/LocalObjectStore`.

## 9. `Launcher/config.json`

Core backtest keys: `"environment": "backtesting"`, `"algorithm-type-name"`,
`"algorithm-language": "CSharp" | "Python"`, `"algorithm-location"` (a DLL, or a
`.py` path such as `"../../../Algorithm.Python/BasicTemplateFrameworkAlgorithm.py"`),
`"data-folder": "../../../Data/"`, `"debugging"`, `"debugging-method"`
(`LocalCmdline`, `VisualStudio`, `Debugpy`, `PyCharm`), `"python-venv"`,
`"parameters": { }` (read via `GetParameter`), `"job-user-id"`, `"api-access-token"`,
`"job-organization-id"`, and the limits `"symbol-minute-limit"`,
`"symbol-second-limit"`, `"symbol-tick-limit"`,
`"maximum-data-points-per-chart-series"`, `"maximum-chart-series"`,
`"force-exchange-always-open"`, `"show-missing-data-logs"`, `"transaction-log"`.

Pluggable handlers: `"log-handler"`, `"messaging-handler"`, `"job-queue-handler"`,
`"api-handler"`, `"map-file-provider"`, `"factor-file-provider"`, `"data-provider"`,
`"object-store"`, `"data-aggregator"`.

The `backtesting` environment sets `"live-mode": false`,
`"setup-handler": BacktestingSetupHandler`, `"result-handler": BacktestingResultHandler`,
`"data-feed-handler": FileSystemDataFeed`, `"real-time-handler": BacktestingRealTimeHandler`,
`"transaction-handler": BacktestingTransactionHandler`.

CLI overrides accepted by `Configuration/LeanArgumentParser.cs`: `--config`,
`--close-automatically`, `--results-destination-folder`, `--backtest-name`,
`--algorithm-id`, `--optimization-id`, `--environment`, `--algorithm-type-name`,
`--algorithm-language`, `--algorithm-location`, `--composer-dll-directory`,
`--data-folder`, plus each handler key.

Running upstream: `dotnet build QuantConnect.Lean.sln`, then
`cd Launcher/bin/Debug && dotnet QuantConnect.Lean.Launcher.dll`. Requires the .NET 10
SDK. Docker images: `Dockerfile`, `DockerfileLeanFoundation`, `DockerfileJupyter`.
CLI: `pip install lean`, then `lean project-create`, `lean backtest`, `lean optimize`,
`lean live`, `lean research`.

## 10. Instructive `Algorithm.Python` files

| File | What it demonstrates |
|---|---|
| `BasicTemplateAlgorithm.py` | minimal skeleton |
| `BasicTemplateFrameworkAlgorithm.py` | canonical five-model wiring |
| `BasicTemplateOptionsAlgorithm.py` | option chains, filters, contract selection |
| `BasicTemplateFuturesAlgorithm.py` | futures chains and expiry filtering |
| `BasicTemplateCryptoAlgorithm.py` | crypto pairs and account currency |
| `CoarseFineFundamentalComboAlgorithm.py` | two-stage coarse→fine universe |
| `CoarseFundamentalTop3Algorithm.py` | simplest dollar-volume universe |
| `EmaCrossUniverseSelectionAlgorithm.py` | indicator-driven dynamic universe |
| `DropboxBaseDataUniverseSelectionAlgorithm.py` | universe from a remote file |
| `CustomDataRegressionAlgorithm.py`, `CustomDataBitcoinAlgorithm.py` | `PythonData` with `get_source`/`reader` |
| `CustomDataNIFTYAlgorithm.py` | multi-source custom data |
| `DataConsolidationAlgorithm.py` | every consolidator flavour |
| `ConsolidateRegressionAlgorithm.py` | the `self.consolidate(...)` helper |
| `CustomIndicatorAlgorithm.py`, `CustomWarmUpPeriodIndicatorAlgorithm.py` | Python indicators with `update` / `warm_up_period` |
| `CustomModelsAlgorithm.py`, `CustomModelsPEP8Algorithm.py` | custom fill, fee and slippage models |
| `CustomBrokerageModelRegressionAlgorithm.py` | subclassing `DefaultBrokerageModel` |
| `CustomSecurityInitializerAlgorithm.py` | per-security model injection |
| `BlackLittermanPortfolioOptimizationFrameworkAlgorithm.py` | Black-Litterman construction |
| `KerasNeuralNetworkAlgorithm.py`, `PytorchNeuralNetworkAlgorithm.py`, `TensorFlowNeuralNetworkAlgorithm.py` | training inside `train()` |
| `TrainingExampleAlgorithm.py`, `ObjectStoreExampleAlgorithm.py` | scheduled training and model persistence |

## 11. Highest-value files

1. `Lean/Algorithm/QCAlgorithm.cs`
2. `Lean/Algorithm/QCAlgorithm.Trading.cs`
3. `Lean/Algorithm/QCAlgorithm.History.cs`
4. `Lean/Algorithm/QCAlgorithm.Indicators.cs`
5. `Lean/Algorithm/QCAlgorithm.Universe.cs`
6. `Lean/Algorithm/QCAlgorithm.Framework.cs`
7. `Lean/Common/Data/Slice.cs`
8. `Lean/Common/Data/BaseData.cs`
9. `Lean/Common/Global.cs`
10. `Lean/Common/Algorithm/Framework/Alphas/Insight.cs`
11. `Lean/Algorithm/Portfolio/PortfolioConstructionModel.cs`
12. `Lean/Launcher/config.json` and `Lean/Configuration/LeanArgumentParser.cs`
