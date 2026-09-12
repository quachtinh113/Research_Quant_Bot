---
name: lean-algorithm-builder
description: "Write, wire and configure QuantConnect LEAN algorithms in Python: QCAlgorithm lifecycle, the five framework models, universes, indicators, custom data, reality modelling and run configuration."
---

# QuantConnect LEAN Algorithm Builder

LEAN is the execution end of this suite. It is an event-driven engine: your algorithm
is called bar by bar, orders go through a fill model, a fee model and a brokerage
model, and the same code path runs a backtest, a paper account and a live account.
Use it when fill mechanics, order types, corporate actions, option and future chains,
or brokerage constraints actually matter to the answer.

Repository: `Lean/` (sparse checkout).

## Read this before you promise a local run

This checkout contains `Algorithm`, `Algorithm.Python`, `Algorithm.Framework`,
`Common`, `Indicators`, `Engine`, `Report`, `Optimizer`, `Api`, `Configuration` and
`Launcher`. It **does not** contain `Data/`, `Tests/`, `Research/`, `ToolBox/`,
`AlgorithmFactory/`, `Algorithm.CSharp/`, `Queues/`, `Messaging/` or `Logging/`.

Consequences, state them plainly rather than discovering them at build time:

- `QuantConnect.Lean.sln` references missing projects, so `dotnet build` fails here.
- `Launcher/config.json` points `data-folder` at `../../../Data/`, which is absent.
- There is **no local market data**, so no backtest can run from this checkout alone.

Use this checkout as the authoritative API reference and to author algorithms. To
actually run them, install the CLI (`pip install lean`, then `lean project-create`,
`lean backtest`, `lean research`, `lean live`), which pulls a complete Docker image
and its data, or run against QuantConnect Cloud.

## Python naming: snake_case

Current LEAN exposes **snake_case** methods and properties and **UPPER_SNAKE** enum
members to Python. PascalCase still resolves through Python.NET, but every current
example uses snake_case and the wrappers call `ToSnakeCase()` when probing.

```python
self.set_start_date(2020, 1, 1)
self.add_equity("SPY", Resolution.DAILY)
self.set_holdings("SPY", 0.5)
insight = Insight.price(symbol, timedelta(days=5), InsightDirection.UP)
if order_event.status == OrderStatus.FILLED: ...
```

Write snake_case. Mixing conventions in one file is the fastest way to produce code
that half works.

## The classic algorithm shape

```python
from AlgorithmImports import *

class MomentumRotation(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(1_000_000)
        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,
                                 AccountType.MARGIN)

        self.symbols = [self.add_equity(t, Resolution.DAILY).symbol
                        for t in ["SPY", "QQQ", "IWM", "EFA", "TLT", "GLD"]]
        self.mom = {s: self.momp(s, 126, Resolution.DAILY) for s in self.symbols}

        self.set_warm_up(126, Resolution.DAILY)
        self.schedule.on(self.date_rules.month_start("SPY"),
                         self.time_rules.after_market_open("SPY", 30),
                         self.rebalance)

    def rebalance(self):
        if self.is_warming_up:
            return
        ranked = sorted((s for s in self.symbols if self.mom[s].is_ready),
                        key=lambda s: self.mom[s].current.value, reverse=True)
        top = ranked[:3]
        for s in self.symbols:
            if s not in top and self.portfolio[s].invested:
                self.liquidate(s)
        for s in top:
            self.set_holdings(s, 1.0 / len(top))

    def on_order_event(self, order_event):
        if order_event.status == OrderStatus.FILLED:
            self.debug(f"{order_event.symbol} {order_event.fill_quantity} @ {order_event.fill_price}")
```

`set_warm_up` plus the `is_warming_up` guard is the LEAN equivalent of shifting a
signal. Without it your first trades are taken on indicators that are not ready.

## The Algorithm Framework

For anything you intend to maintain, prefer the five-model framework over one large
`on_data`. Each model is separately testable and separately replaceable.

| Model | Interface | Required override |
|---|---|---|
| Universe selection | `IUniverseSelectionModel` | `create_universes(algorithm)` |
| Alpha | `IAlphaModel` | `update(algorithm, data) -> Iterable[Insight]` |
| Portfolio construction | `IPortfolioConstructionModel` | `create_targets(algorithm, insights)` or `determine_target_percent(active_insights)` |
| Execution | `IExecutionModel` | `execute(algorithm, targets)` |
| Risk management | `IRiskManagementModel` | `manage_risk(algorithm, targets)` |

```python
def initialize(self):
    self.set_start_date(2018, 1, 1)
    self.set_cash(1_000_000)
    self.universe_settings.resolution = Resolution.DAILY

    self.set_universe_selection(QC500UniverseSelectionModel())
    self.set_alpha(EmaCrossAlphaModel(fast_period=20, slow_period=100,
                                      resolution=Resolution.DAILY))
    self.set_portfolio_construction(InsightWeightingPortfolioConstructionModel())
    self.set_execution(VolumeWeightedAveragePriceExecutionModel())
    self.set_risk_management(MaximumDrawdownPercentPortfolio(0.15))
```

The separation is what lets `quant-mentor` audit the alpha independently of the
sizing, and it is why the same alpha can be re-costed under a different execution
model without touching the signal.

## Insights are the contract between alpha and sizing

```python
Insight.price(symbol, timedelta(days=5), InsightDirection.UP,
              magnitude=0.02, confidence=0.6, weight=0.1)
```

`direction` drives the sign, `weight` drives `InsightWeightingPortfolioConstructionModel`,
`confidence` drives `ConfidenceWeightedPortfolioConstructionModel`, and `period` is
how long the view is live. An insight with no period expires immediately and produces
nothing.

## Reality modelling is not optional

LEAN's default models are already more honest than most backtesters, but they are
still defaults. State them explicitly:

```python
def initialize(self):
    self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
    self.set_security_initializer(self.custom_initializer)

def custom_initializer(self, security):
    security.set_fee_model(InteractiveBrokersFeeModel())
    security.set_slippage_model(VolumeShareSlippageModel(volume_limit=0.025,
                                                        price_impact=0.1))
    security.set_fill_model(EquityFillModel())
```

`VolumeShareSlippageModel` is the honest default for equities because it makes your
cost a function of how much of the bar's volume you take. A `ConstantSlippageModel`
lets a strategy pretend it can trade any size.

## Guards specific to LEAN

1. **Set the brokerage model.** It constrains order types, leverage and the fee
   schedule. Leaving it at default silently permits orders your broker would reject.
2. **Warm up indicators** and guard on `is_warming_up`.
3. **`history` returns a pandas DataFrame in Python.** It is a lookback and is safe.
   Building a feature from `history` inside `initialize` and then reusing it for the
   whole backtest is not — refresh it as the algorithm advances.
4. **Universe changes arrive through `on_securities_changed`.** Clean up indicators
   and consolidators for removed securities or you leak memory and stale state.
5. **`set_holdings` targets a fraction of *portfolio value*,** which moves as the
   portfolio moves. It is not a fixed notional.
6. **Corporate actions arrive in the `Slice`.** Handle `slice.splits` and
   `slice.dividends` if your logic depends on price levels.

## References

- Full API surface, framework models, indicators, data model, config keys:
  [api-reference.md](references/api-reference.md)
- Runnable algorithm patterns: [recipes.md](references/recipes.md)
- Auto-generated repository map: [project-structure.md](references/project-structure.md)
- Auto-generated dependency map: [tech-stacks.md](references/tech-stacks.md)

## Related skills

`execution-costs-microstructure` to choose fee and slippage models, `vectorbt-backtest`
to prototype before writing LEAN code, `portfolio-construction-risk` to replace the
default portfolio construction model, `live-deployment-monitoring` for the path from
backtest to a funded account.
