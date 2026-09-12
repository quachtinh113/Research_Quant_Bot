"""
Reference pod: Donchian volatility breakout with realised-volatility regime
gating. Suitable for BTC/USDT (24x7) or XAU/USD.

All features are computed on the closed-bar history the feed hands over; the
current bar is the latest *closed* bar and the channel is built on bars
strictly before it.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from orchestration.constants import MarketRegime, OrderSide, OrderType, SignalDirection, TimeInForce, VolatilityState
from orchestration.builder_core.feed.bar_feed import Bar
from orchestration.mentor_core.risk_engine.central_risk import PositionSizingResult
from orchestration.schemas import ExecutionParamsSchema, ExecutionPayloadSchema, RegimeSchema, SignalSchema
from .base_pod import BasePod


class VolatilityBreakoutPod(BasePod):
    def __init__(
        self,
        instance_id: str = "POD_BTCUSDT_VOL_BREAKOUT",
        symbol: str = "BTC/USDT",
        lookback_period: int = 20,
        initial_equity: float = 100_000.0,
        bar_interval: str = "5min",
        market_order_confidence: float = 0.8,
        max_slippage_bps: int = 5,
        **kwargs,
    ) -> None:
        super().__init__(instance_id=instance_id, symbol=symbol, initial_equity=initial_equity, bar_interval=bar_interval, **kwargs)
        self.lookback_period = lookback_period
        self.market_order_confidence = market_order_confidence
        self.max_slippage_bps = max_slippage_bps
        seconds = self.bar_interval.total_seconds()
        self.periods_per_year = 365.0 * 24.0 * 3600.0 / seconds if seconds > 0 else 365.0

    # ---------------------------------------------------------------- regime
    def detect_regime(self, history_df: pd.DataFrame) -> RegimeSchema:
        if len(history_df) < self.lookback_period + 1:
            return RegimeSchema(
                type=MarketRegime.LOW_VOL_COMPRESSION,
                volatility_state=VolatilityState.LOW,
                liquidity_assessment="Insufficient bar history for statistical depth.",
            )
        closes = history_df["close"]
        returns = closes.pct_change().dropna()
        rv = float(returns.iloc[-self.lookback_period :].std() * np.sqrt(self.periods_per_year))
        rv = 0.0 if np.isnan(rv) else rv

        if rv > 0.80:
            vol_state = VolatilityState.EXTREME
        elif rv > 0.50:
            vol_state = VolatilityState.HIGH
        elif rv < 0.20:
            vol_state = VolatilityState.LOW
        else:
            vol_state = VolatilityState.NORMAL

        last_ret = abs(float(returns.iloc[-1])) if len(returns) else 0.0
        bar_sigma = float(returns.iloc[-self.lookback_period :].std()) or 1e-9
        vol_ratio = history_df["volume"].iloc[-1] / max(history_df["volume"].iloc[-self.lookback_period :].mean(), 1e-9)
        if last_ret > 4.0 * bar_sigma and vol_ratio > 2.0:
            return RegimeSchema(
                type=MarketRegime.LIQUIDITY_SHOCK,
                volatility_state=VolatilityState.EXTREME,
                liquidity_assessment=f"Shock bar: |ret| {last_ret*100:.2f}% at {vol_ratio:.1f}x volume.",
            )

        ma_fast = closes.rolling(max(2, self.lookback_period // 2)).mean().iloc[-1]
        ma_slow = closes.rolling(self.lookback_period).mean().iloc[-1]
        spread = abs(ma_fast - ma_slow) / ma_slow if ma_slow else 0.0

        if vol_state in (VolatilityState.HIGH, VolatilityState.EXTREME):
            if spread < 0.005:
                regime = MarketRegime.HIGH_VOL_RANGING
            else:
                regime = MarketRegime.TRENDING_BULL if ma_fast > ma_slow else MarketRegime.TRENDING_BEAR
        elif vol_state == VolatilityState.LOW:
            regime = MarketRegime.LOW_VOL_COMPRESSION
        else:
            regime = MarketRegime.TRENDING_BULL if ma_fast >= ma_slow else MarketRegime.TRENDING_BEAR

        return RegimeSchema(
            type=regime,
            volatility_state=vol_state,
            liquidity_assessment=f"{self.lookback_period}-bar realised vol {rv*100:.1f}% annualised; volume ratio {vol_ratio:.2f}.",
        )

    # ---------------------------------------------------------------- signal
    def generate_signal(self, history_df: pd.DataFrame, current_bar: Bar) -> SignalSchema:
        if len(history_df) < self.lookback_period + 1:
            return SignalSchema(direction=SignalDirection.NEUTRAL, confidence_score=0.0, primary_factors=["INSUFFICIENT_DATA"])

        # Channel built on bars strictly before the current closed bar.
        past = history_df.iloc[:-1]
        upper = float(past["high"].rolling(self.lookback_period).max().iloc[-1])
        lower = float(past["low"].rolling(self.lookback_period).min().iloc[-1])

        if current_bar.close > upper:
            edge = (current_bar.close - upper) / upper
            return SignalSchema(
                direction=SignalDirection.BUY,
                confidence_score=round(float(min(1.0, 0.6 + edge / 0.01)), 4),
                primary_factors=["DONCHIAN_UPPER_BREAKOUT", "VOLATILITY_EXPANSION"],
            )
        if current_bar.close < lower:
            edge = (lower - current_bar.close) / lower
            return SignalSchema(
                direction=SignalDirection.SELL,
                confidence_score=round(float(min(1.0, 0.6 + edge / 0.01)), 4),
                primary_factors=["DONCHIAN_LOWER_BREAKDOWN", "VOLATILITY_EXPANSION"],
            )
        return SignalSchema(direction=SignalDirection.NEUTRAL, confidence_score=0.0, primary_factors=["IN_CHANNEL_CONSOLIDATION"])

    # ------------------------------------------------------------- execution
    def build_execution_payload(
        self, signal: SignalSchema, risk_result: PositionSizingResult, current_bar: Bar
    ) -> ExecutionPayloadSchema:
        side = OrderSide.BUY if signal.direction == SignalDirection.BUY else OrderSide.SELL
        order_type = OrderType.MARKET if signal.confidence_score >= self.market_order_confidence else OrderType.LIMIT
        return ExecutionPayloadSchema(
            exchange_standard="CCXT",
            order_type=order_type,
            side=side,
            price=current_bar.close,
            amount=risk_result.units if risk_result.allowed else 0.0,
            params=ExecutionParamsSchema(timeInForce=TimeInForce.GTC, max_slippage_bps=self.max_slippage_bps),
        )

    # ---------------------------------------------------------------- thesis
    def formulate_thesis(self, regime: RegimeSchema, signal: SignalSchema, risk_result: PositionSizingResult) -> str:
        if signal.direction == SignalDirection.NEUTRAL:
            return (
                f"Neutral: price inside the {self.lookback_period}-bar Donchian channel. "
                f"Regime {regime.type.value}, volatility {regime.volatility_state.value}."
            )
        base = (
            f"{signal.direction.value} breakout in {regime.type.value} regime, confidence {signal.confidence_score:.2f} "
            f"from {', '.join(signal.primary_factors)}."
        )
        if risk_result.allowed:
            return base + (
                f" Central Risk Engine sized {risk_result.position_pct*100:.2f}% of equity, "
                f"hard stop {risk_result.stop_loss_price:.2f}, R:R {risk_result.risk_reward_ratio:.2f}."
            )
        return base + f" Central Risk Engine rejected entry: {risk_result.rejection_reason}"
