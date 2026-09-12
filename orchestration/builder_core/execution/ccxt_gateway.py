"""
CCXT unified execution gateway.

Two modes share one code path up to the exchange call:

* PAPER: deterministic fill simulation with configurable slippage and fees.
* LIVE:  ``ccxt.async_support`` order placement with bounded retries, order
         status polling, timeout cancellation and post-trade slippage audit.

Before either mode touches an order the amount and price are normalised to
the exchange's precision grid and checked against ``min_amount``,
``max_amount`` and ``min_cost`` limits.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from orchestration.config import ExecutionSettings, RateLimitSettings
from orchestration.constants import ExecutionMode, OrderSide, OrderStatus, OrderType, TimeInForce
from orchestration.mentor_core.guards.rate_limit import RateLimiter, retry_async

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    success: bool
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    executed_price: float
    executed_amount: float
    cost: float
    fee: float
    slippage_bps: float
    status: OrderStatus = OrderStatus.FILLED
    requested_price: float = 0.0
    requested_amount: float = 0.0
    latency_ms: float = 0.0
    slippage_breach: bool = False
    error_message: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def rejected(
        cls,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        reason: str,
        requested_price: float = 0.0,
        requested_amount: float = 0.0,
        status: OrderStatus = OrderStatus.REJECTED,
    ) -> "ExecutionResult":
        return cls(
            success=False,
            order_id="",
            symbol=symbol,
            side=side,
            order_type=order_type,
            executed_price=0.0,
            executed_amount=0.0,
            cost=0.0,
            fee=0.0,
            slippage_bps=0.0,
            status=status,
            requested_price=requested_price,
            requested_amount=requested_amount,
            error_message=reason,
        )


@dataclass(frozen=True)
class MarketRules:
    price_precision: int = 2
    amount_precision: int = 4
    min_amount: float = 0.0
    max_amount: Optional[float] = None
    min_cost: float = 5.0


@dataclass
class NormalizedOrder:
    is_valid: bool
    normalized_price: float
    normalized_amount: float
    cost: float
    min_cost: float
    reason: Optional[str] = None


SlippageModel = Callable[[str, OrderSide, OrderType, float, float], float]
"""(symbol, side, order_type, price, amount) -> slippage in bps (adverse)."""


def _floor_to_decimals(value: float, decimals: int) -> float:
    factor = 10.0 ** decimals
    return math.floor(value * factor + 1e-9) / factor


class CCXTExecutionGateway:
    def __init__(
        self,
        exchange_id: str = "binance",
        mode: ExecutionMode = ExecutionMode.PAPER,
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        settings: Optional[ExecutionSettings] = None,
        rate_limiter: Optional[RateLimiter] = None,
        rate_limit_settings: Optional[RateLimitSettings] = None,
        market_rules: Optional[Dict[str, MarketRules]] = None,
        slippage_model: Optional[SlippageModel] = None,
        is_live: Optional[bool] = None,  # backwards-compat flag
    ) -> None:
        self.settings = settings or ExecutionSettings(exchange_id=exchange_id, api_key=api_key, secret=secret)
        if is_live is not None:
            mode = ExecutionMode.LIVE if is_live else ExecutionMode.PAPER
        elif settings is not None and settings.live:
            mode = ExecutionMode.LIVE
        self.exchange_id = self.settings.exchange_id
        self.mode = mode
        self.market_rules: Dict[str, MarketRules] = dict(market_rules or {})
        self.slippage_model = slippage_model
        self._rl_settings = rate_limit_settings or RateLimitSettings()
        self.rate_limiter = rate_limiter or RateLimiter(self._rl_settings.tokens, self._rl_settings.period_sec)
        self.exchange = None
        self.markets: Dict[str, Any] = {}
        self.open_orders: Dict[str, Dict[str, Any]] = {}
        self.order_log: List[ExecutionResult] = []
        self._sim_seq = 0
        if self.mode == ExecutionMode.LIVE:
            self._init_exchange()

    # ------------------------------------------------------------- lifecycle
    @property
    def is_live(self) -> bool:
        return self.mode == ExecutionMode.LIVE

    def _init_exchange(self) -> None:
        try:
            import ccxt.async_support as ccxt_async  # type: ignore

            cls = getattr(ccxt_async, self.exchange_id, None)
            if cls is None:
                raise ValueError(f"Unknown CCXT exchange id: {self.exchange_id}")
            cfg: Dict[str, Any] = {"enableRateLimit": True}
            if self.settings.api_key and self.settings.secret:
                cfg.update({"apiKey": self.settings.api_key, "secret": self.settings.secret})
            self.exchange = cls(cfg)
        except Exception as exc:
            logger.error("CCXT exchange init failed: %s", exc)
            self.exchange = None

    async def load_markets(self) -> None:
        if self.exchange is None:
            return
        await self.rate_limiter.acquire()
        self.markets = await self.exchange.load_markets()

    async def close(self) -> None:
        if self.exchange is not None:
            try:
                await self.exchange.close()
            except Exception:  # pragma: no cover
                pass

    # ------------------------------------------------------------ precision
    def rules_for(self, symbol: str) -> MarketRules:
        if symbol in self.market_rules:
            return self.market_rules[symbol]
        market = self.markets.get(symbol) if self.markets else None
        if market:
            prec = market.get("precision", {}) or {}
            limits = market.get("limits", {}) or {}

            def _decimals(v: Any, default: int) -> int:
                if v is None:
                    return default
                if isinstance(v, int):
                    return v
                if isinstance(v, float) and v < 1:  # tick size, e.g. 0.001
                    return max(0, int(round(-math.log10(v))))
                return default

            return MarketRules(
                price_precision=_decimals(prec.get("price"), 2),
                amount_precision=_decimals(prec.get("amount"), 4),
                min_amount=float((limits.get("amount") or {}).get("min") or 0.0),
                max_amount=(limits.get("amount") or {}).get("max"),
                min_cost=float((limits.get("cost") or {}).get("min") or 0.0),
            )
        return MarketRules()

    def normalize_order(self, symbol: str, price: float, amount: float, **_: Any) -> NormalizedOrder:
        rules = self.rules_for(symbol)
        if self.exchange is not None and self.markets and symbol in self.markets:
            try:
                norm_price = float(self.exchange.price_to_precision(symbol, price))
                norm_amount = float(self.exchange.amount_to_precision(symbol, amount))
            except Exception:
                norm_price = _floor_to_decimals(price, rules.price_precision)
                norm_amount = _floor_to_decimals(amount, rules.amount_precision)
        else:
            norm_price = _floor_to_decimals(price, rules.price_precision)
            norm_amount = _floor_to_decimals(amount, rules.amount_precision)

        cost = norm_price * norm_amount
        reason = None
        if norm_amount <= 0:
            reason = "Amount rounds to zero at exchange precision."
        elif norm_amount < rules.min_amount:
            reason = f"Amount {norm_amount} below exchange min_amount {rules.min_amount}."
        elif rules.max_amount is not None and norm_amount > rules.max_amount:
            reason = f"Amount {norm_amount} above exchange max_amount {rules.max_amount}."
        elif cost < rules.min_cost:
            reason = f"Notional {cost:.4f} below exchange min_cost {rules.min_cost}."
        return NormalizedOrder(reason is None, norm_price, norm_amount, cost, rules.min_cost, reason)

    # ------------------------------------------------------------ execution
    async def execute_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        target_price: float,
        amount: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
        max_slippage_bps: Optional[int] = None,
        timeout_sec: Optional[float] = None,
    ) -> ExecutionResult:
        max_slip = self.settings.default_max_slippage_bps if max_slippage_bps is None else max_slippage_bps
        norm = self.normalize_order(symbol, target_price, amount)
        if not norm.is_valid:
            res = ExecutionResult.rejected(symbol, side, order_type, f"Order rejected: {norm.reason}", target_price, amount)
            self.order_log.append(res)
            return res

        if self.is_live:
            res = await self._execute_live(symbol, side, order_type, norm, target_price, time_in_force, max_slip, timeout_sec)
        else:
            res = self._execute_paper(symbol, side, order_type, norm, target_price, max_slip)
        self.order_log.append(res)
        return res

    # --- paper -------------------------------------------------------------
    def _execute_paper(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        norm: NormalizedOrder,
        target_price: float,
        max_slip: float,
    ) -> ExecutionResult:
        t0 = time.perf_counter()
        if self.slippage_model is not None:
            slip_bps = float(self.slippage_model(symbol, side, order_type, norm.normalized_price, norm.normalized_amount))
        elif order_type in (OrderType.LIMIT, OrderType.LIMIT_MAKER):
            slip_bps = self.settings.sim_limit_slippage_bps
        else:
            slip_bps = self.settings.sim_market_slippage_bps

        is_maker = order_type in (OrderType.LIMIT, OrderType.LIMIT_MAKER)
        if slip_bps > max_slip and not is_maker:
            # Market order would be filled beyond tolerance: reject before sending.
            return ExecutionResult.rejected(
                symbol, side, order_type,
                f"Simulated slippage {slip_bps:.2f} bps exceeds max {max_slip} bps.",
                target_price, norm.normalized_amount,
            )
        adverse = 1.0 + (slip_bps / 10_000.0 if side == OrderSide.BUY else -slip_bps / 10_000.0)
        rules = self.rules_for(symbol)
        fill_price = round(norm.normalized_price * adverse, rules.price_precision)
        cost = fill_price * norm.normalized_amount
        fee_bps = self.settings.maker_fee_bps if is_maker else self.settings.taker_fee_bps
        fee = cost * fee_bps / 10_000.0
        self._sim_seq += 1
        return ExecutionResult(
            success=True,
            order_id=f"SIM-{self._sim_seq:08d}",
            symbol=symbol,
            side=side,
            order_type=order_type,
            executed_price=fill_price,
            executed_amount=norm.normalized_amount,
            cost=cost,
            fee=fee,
            slippage_bps=abs(fill_price - target_price) / target_price * 10_000.0 if target_price else 0.0,
            status=OrderStatus.FILLED,
            requested_price=target_price,
            requested_amount=norm.normalized_amount,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
        )

    # --- live --------------------------------------------------------------
    async def _execute_live(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        norm: NormalizedOrder,
        target_price: float,
        time_in_force: TimeInForce,
        max_slip: float,
        timeout_sec: Optional[float],
    ) -> ExecutionResult:
        if self.exchange is None:
            return ExecutionResult.rejected(symbol, side, order_type, "Live mode requested but CCXT exchange unavailable.")
        timeout = timeout_sec or self.settings.order_timeout_sec
        t0 = time.perf_counter()
        ccxt_type = "market" if order_type == OrderType.MARKET else "limit"
        params: Dict[str, Any] = {}
        if ccxt_type == "limit":
            params["timeInForce"] = time_in_force.value
            if order_type == OrderType.LIMIT_MAKER or time_in_force == TimeInForce.PostOnly:
                params["postOnly"] = True

        try:
            raw = await self._create_order_with_retry(
                symbol, ccxt_type, side.value, norm.normalized_amount,
                None if ccxt_type == "market" else norm.normalized_price, params,
            )
        except Exception as exc:
            return ExecutionResult.rejected(symbol, side, order_type, f"CCXT create_order failed: {exc}", target_price, norm.normalized_amount)

        order_id = str(raw.get("id", ""))
        self.open_orders[order_id] = raw
        deadline = time.monotonic() + timeout
        order = raw
        while time.monotonic() < deadline:
            status = (order.get("status") or "").lower()
            if status in ("closed", "filled") or float(order.get("remaining") or 0.0) == 0.0 and float(order.get("filled") or 0.0) > 0:
                break
            if status in ("canceled", "rejected", "expired"):
                break
            await asyncio.sleep(min(0.5, max(0.05, timeout / 20)))
            try:
                await self.rate_limiter.acquire()
                order = await self.exchange.fetch_order(order_id, symbol)
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning("fetch_order failed for %s: %s", order_id, exc)
        else:
            # Timed out: cancel remainder.
            try:
                await self.rate_limiter.acquire()
                await self.exchange.cancel_order(order_id, symbol)
                order = await self.exchange.fetch_order(order_id, symbol)
            except Exception as exc:  # pragma: no cover
                logger.warning("cancel_order failed for %s: %s", order_id, exc)

        self.open_orders.pop(order_id, None)
        filled = float(order.get("filled") or 0.0)
        avg_price = float(order.get("average") or order.get("price") or norm.normalized_price)
        status_raw = (order.get("status") or "").lower()
        fee_info = order.get("fee") or {}
        fee = float(fee_info.get("cost") or (avg_price * filled * self.settings.taker_fee_bps / 10_000.0))
        slip_bps = abs(avg_price - target_price) / target_price * 10_000.0 if target_price else 0.0
        if filled <= 0:
            st = OrderStatus.CANCELED if status_raw == "canceled" else OrderStatus.EXPIRED
            return ExecutionResult.rejected(symbol, side, order_type, f"No fill within {timeout}s (status={status_raw}).", target_price, norm.normalized_amount, status=st)
        status = OrderStatus.FILLED if filled >= norm.normalized_amount - 1e-12 else OrderStatus.PARTIALLY_FILLED
        return ExecutionResult(
            success=True,
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            executed_price=avg_price,
            executed_amount=filled,
            cost=avg_price * filled,
            fee=fee,
            slippage_bps=slip_bps,
            status=status,
            requested_price=target_price,
            requested_amount=norm.normalized_amount,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            slippage_breach=slip_bps > max_slip,
            raw=order,
        )

    async def _create_order_with_retry(self, symbol, ccxt_type, side, amount, price, params):
        try:
            import ccxt  # type: ignore

            transient = (ccxt.NetworkError, ccxt.RequestTimeout, ccxt.DDoSProtection, ccxt.ExchangeNotAvailable)
        except Exception:  # pragma: no cover
            transient = (ConnectionError, TimeoutError)

        rl = self._rl_settings

        @retry_async(rl.retry_max_attempts, rl.retry_base_delay_sec, rl.retry_factor, rl.retry_max_delay_sec, transient)
        async def _send():
            await self.rate_limiter.acquire()
            return await self.exchange.create_order(symbol, ccxt_type, side, amount, price, params)

        return await _send()

    # ------------------------------------------------------------- data
    async def fetch_closed_ohlcv(
        self, symbol: str, timeframe: str = "5m", since_ms: Optional[int] = None, limit: int = 500
    ) -> pd.DataFrame:
        """
        Fetch OHLCV and drop the still-forming last candle so only closed bars
        reach the pods. Index = bar close time (UTC).
        """
        if self.exchange is None:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        await self.rate_limiter.acquire()
        rows = await self.exchange.fetch_ohlcv(symbol, timeframe, since_ms, limit)
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(rows, columns=["open_ms", "open", "high", "low", "close", "volume"])
        interval = pd.Timedelta(self.exchange.parse_timeframe(timeframe), unit="s")
        df["timestamp"] = pd.to_datetime(df["open_ms"], unit="ms", utc=True) + interval
        df = df.set_index("timestamp").drop(columns=["open_ms"])
        now = pd.Timestamp.now(tz="UTC")
        return df[df.index <= now]
