# LEAN Recipes

All Python, all snake_case, all starting from `from AlgorithmImports import *`.

## Recipe 1 — Framework algorithm with a custom alpha

```python
from AlgorithmImports import *
from datetime import timedelta


class MomentumAlpha(AlphaModel):

    def __init__(self, period=126, resolution=Resolution.DAILY):
        self.period = period
        self.resolution = resolution
        self.indicators = {}
        self.name = f"{self.__class__.__name__}({period})"

    def update(self, algorithm, data):
        insights = []
        ready = {s: i for s, i in self.indicators.items() if i.is_ready}
        if len(ready) < 3:
            return insights
        ranked = sorted(ready, key=lambda s: ready[s].current.value, reverse=True)
        for symbol in ranked[:3]:
            if data.contains_key(symbol) and data[symbol] is not None:
                insights.append(Insight.price(
                    symbol, timedelta(days=21), InsightDirection.UP,
                    magnitude=float(ready[symbol].current.value),
                    confidence=0.5, weight=1.0 / 3.0,
                    source_model=self.name,
                ))
        return insights

    def on_securities_changed(self, algorithm, changes):
        for security in changes.added_securities:
            self.indicators[security.symbol] = algorithm.momp(
                security.symbol, self.period, self.resolution)
        for security in changes.removed_securities:
            indicator = self.indicators.pop(security.symbol, None)
            if indicator is not None:
                algorithm.deregister_indicator(indicator)


class FrameworkMomentum(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2016, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(1_000_000)
        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,
                                 AccountType.MARGIN)
        self.universe_settings.resolution = Resolution.DAILY

        tickers = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ"]
        symbols = [Symbol.create(t, SecurityType.EQUITY, Market.USA) for t in tickers]

        self.set_universe_selection(ManualUniverseSelectionModel(symbols))
        self.set_alpha(MomentumAlpha(period=126))
        self.set_portfolio_construction(InsightWeightingPortfolioConstructionModel())
        self.set_execution(VolumeWeightedAveragePriceExecutionModel())
        self.set_risk_management(MaximumDrawdownPercentPortfolio(0.20))
```

The `deregister_indicator` in `on_securities_changed` is the part people skip. Without
it, a dynamic universe accumulates indicators for securities you no longer hold.

## Recipe 2 — Explicit reality modelling

```python
class RealisticCosts(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_cash(1_000_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,
                                 AccountType.MARGIN)
        self.set_security_initializer(self._initialize_security)
        self.add_equity("SPY", Resolution.MINUTE)

    def _initialize_security(self, security):
        security.set_fee_model(InteractiveBrokersFeeModel())
        security.set_slippage_model(VolumeShareSlippageModel(
            volume_limit=0.025, price_impact=0.10))
        security.set_fill_model(EquityFillModel())
        security.set_leverage(1.0)
```

`volume_limit=0.025` caps you at 2.5% of the bar's volume. If a strategy needs more,
it has a capacity problem, and this model will show it as unfilled orders rather than
hiding it in an optimistic average price.

## Recipe 3 — Custom fee, slippage and fill models

```python
class BpsFeeModel(FeeModel):
    def __init__(self, bps=5.0):
        self.rate = bps / 10_000.0

    def get_order_fee(self, parameters):
        security, order = parameters.security, parameters.order
        notional = abs(order.get_value(security))
        return OrderFee(CashAmount(notional * self.rate,
                                   security.quote_currency.symbol))


class SpreadSlippageModel:
    def __init__(self, spread_fraction=0.5):
        self.spread_fraction = spread_fraction

    def get_slippage_approximation(self, asset, order):
        spread = asset.ask_price - asset.bid_price
        if spread <= 0:
            return asset.price * 0.0005
        return spread * self.spread_fraction
```

Half the quoted spread is the standard assumption for a marketable order. State the
assumption in a comment so an auditor does not have to reverse-engineer it.

## Recipe 4 — Fundamental universe, single stage

```python
class FundamentalUniverse(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_cash(1_000_000)
        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.select)

    def select(self, fundamental):
        liquid = [f for f in fundamental
                  if f.has_fundamental_data
                  and f.price > 5
                  and f.dollar_volume > 10_000_000]
        by_value = sorted(liquid,
                          key=lambda f: f.valuation_ratios.earning_yield,
                          reverse=True)
        return [f.symbol for f in by_value[:50]]

    def on_securities_changed(self, changes):
        for security in changes.removed_securities:
            if security.invested:
                self.liquidate(security.symbol, tag="left universe")
```

Liquidating on removal is mandatory. A security that leaves the universe stops
receiving data, and a position in it silently freezes.

## Recipe 5 — Scheduled rebalance separate from the data handler

```python
def initialize(self):
    self.set_start_date(2018, 1, 1)
    self.set_cash(1_000_000)
    self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

    self.schedule.on(
        self.date_rules.month_start(self.spy),
        self.time_rules.after_market_open(self.spy, 30),
        self.rebalance,
    )
    self.schedule.on(
        self.date_rules.every_day(self.spy),
        self.time_rules.before_market_close(self.spy, 10),
        self.check_risk,
    )
```

Keeping rebalancing in a scheduled event rather than inside `on_data` makes the
trading cadence explicit and testable, and it stops a minute-resolution subscription
from accidentally producing minute-frequency turnover.

## Recipe 6 — Custom data from a URL

```python
class SentimentData(PythonData):

    def get_source(self, config, date, is_live):
        return SubscriptionDataSource(
            "https://example.com/sentiment.csv",
            SubscriptionTransportMedium.REMOTE_FILE,
        )

    def reader(self, config, line, date, is_live):
        if not line or not line[0].isdigit():
            return None
        parts = line.split(",")
        point = SentimentData()
        point.symbol = config.symbol
        point.time = datetime.strptime(parts[0], "%Y-%m-%d")
        point.end_time = point.time + timedelta(days=1)   # availability, not observation
        point.value = float(parts[1])
        point["score"] = float(parts[1])
        return point
```

`end_time` is the point-in-time control. LEAN delivers the point at `end_time`, so
setting it to the timestamp the data was actually published, not the period it
describes, is what prevents lookahead.

## Recipe 7 — Options with a chain filter

```python
def initialize(self):
    self.set_start_date(2020, 1, 1)
    self.set_cash(250_000)
    option = self.add_option("SPY", Resolution.MINUTE)
    option.set_filter(lambda u: u.strikes(-5, 5).expiration(20, 60).include_weeklys())
    self.option_symbol = option.symbol

def on_data(self, slice):
    chain = slice.option_chains.get(self.option_symbol)
    if chain is None:
        return
    puts = [c for c in chain if c.right == OptionRight.PUT]
    if not puts:
        return
    atm = min(puts, key=lambda c: abs(c.strike - chain.underlying.price))
    if not self.portfolio.invested:
        self.market_order(atm.symbol, -1)
```

Filter aggressively. An unfiltered SPY option chain is tens of thousands of contracts
per day and will dominate the run time and the memory.

## Recipe 8 — Training a model inside the algorithm

```python
def initialize(self):
    self.set_start_date(2018, 1, 1)
    self.set_cash(500_000)
    self.symbol = self.add_equity("SPY", Resolution.DAILY).symbol
    self.model = None
    self.train(self.date_rules.month_start(), self.time_rules.at(8, 0), self.fit)

def fit(self):
    history = self.history(self.symbol, 756, Resolution.DAILY)
    if history.empty:
        return
    close = history["close"].unstack(level=0).iloc[:, 0]
    features = pd.DataFrame({
        "r1": close.pct_change(1), "r5": close.pct_change(5),
        "r21": close.pct_change(21),
        "vol21": close.pct_change().rolling(21).std(),
    })
    target = close.pct_change(5).shift(-5)          # forward return
    frame = pd.concat([features, target.rename("y")], axis=1).dropna()
    if len(frame) < 200:
        return
    from sklearn.linear_model import Ridge
    self.model = Ridge(alpha=1.0).fit(frame.drop(columns="y"), frame["y"])
    self.object_store.save_bytes("model", pickle.dumps(self.model))
```

`self.train` runs the fit outside the data-handling thread so it does not block the
event loop. The forward-shifted target is fine here because it is only ever used on
history that is already in the past at the moment of fitting.

## Recipe 9 — Parameters for the optimiser

```python
def initialize(self):
    fast = int(self.get_parameter("fast_period", 20))
    slow = int(self.get_parameter("slow_period", 100))
    self.fast = self.ema(self.symbol, fast, Resolution.DAILY)
    self.slow = self.ema(self.symbol, slow, Resolution.DAILY)
```

Declare the same keys in `Launcher/config.json` under `"parameters"`, then sweep with
`lean optimize`. Record the number of combinations: it is the trial count that
`backtest-risk-audit` needs.

## Recipe 10 — Porting a vectorbt prototype to LEAN

| vectorbt | LEAN |
|---|---|
| `entries.vbt.signals.fshift(1)` | act in a scheduled event, or set `price=open` semantics by trading at market open |
| `fees=0.0005` | `security.set_fee_model(...)` or `SetBrokerageModel` |
| `slippage=0.0005` | `security.set_slippage_model(VolumeShareSlippageModel(...))` |
| `size_type="targetpercent"` | `self.set_holdings(symbol, weight)` |
| `group_by=True, cash_sharing=True` | inherent: LEAN always has one portfolio |
| `pf.stats()` | the backtest statistics panel, or `Report/` |
| grid over columns | `lean optimize` with `get_parameter` |

Expect the LEAN Sharpe to be lower. That gap is the cost of fill realism, and it is
the number worth understanding rather than explaining away.
