"""
Order manager and pod position ledger.

Tracks one net position per symbol, realised and unrealised PnL, peak equity
and drawdown. State is only restored when ``restore()`` is called explicitly
with a snapshot; nothing is loaded implicitly from disk.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from orchestration.constants import ExitReason, OrderSide
from .ccxt_gateway import ExecutionResult


@dataclass
class Position:
    symbol: str
    side: OrderSide
    amount: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    unrealized_pnl: float = 0.0
    opened_at: Optional[str] = None

    @property
    def notional(self) -> float:
        return self.amount * self.current_price

    def update_pnl(self, mark_price: float) -> None:
        self.current_price = mark_price
        direction = 1.0 if self.side == OrderSide.BUY else -1.0
        self.unrealized_pnl = (mark_price - self.entry_price) * self.amount * direction

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.name
        d["notional"] = self.notional
        return d


@dataclass
class TradeRecord:
    symbol: str
    side: OrderSide  # side of the *closed* position
    amount: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct_equity: float
    fee: float
    reason: ExitReason
    closed_at: Optional[str] = None


class OrderManager:
    def __init__(self, pod_id: str, initial_equity: float = 100_000.0) -> None:
        self.pod_id = pod_id
        self.initial_equity = float(initial_equity)
        self.equity = float(initial_equity)  # cash + realised PnL - fees
        self.peak_equity = float(initial_equity)
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[ExecutionResult] = []
        self.closed_trades: List[TradeRecord] = []
        self.equity_curve: List[float] = [float(initial_equity)]
        self.realized_pnl = 0.0
        self.fees_paid = 0.0

    # ---------------------------------------------------------------- state
    @property
    def current_equity(self) -> float:
        return self.equity + sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def current_drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.current_equity) / self.peak_equity)

    @property
    def gross_notional(self) -> float:
        return sum(p.notional for p in self.positions.values())

    @property
    def margin_utilization_pct(self) -> float:
        eq = self.current_equity
        return (self.gross_notional / eq * 100.0) if eq > 0 else 0.0

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def _update_peak(self) -> None:
        eq = self.current_equity
        if eq > self.peak_equity:
            self.peak_equity = eq

    def mark_to_market(self, symbol: str, price: float) -> None:
        pos = self.positions.get(symbol)
        if pos is not None:
            pos.update_pnl(price)
        self._update_peak()

    def end_of_bar(self) -> float:
        """Append the equity curve; returns the simple return for this bar."""
        eq = self.current_equity
        prev = self.equity_curve[-1]
        self.equity_curve.append(eq)
        return (eq - prev) / prev if prev > 0 else 0.0

    # ---------------------------------------------------------------- fills
    def record_fill(
        self,
        fill: ExecutionResult,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        reason: ExitReason = ExitReason.SIGNAL_FLIP,
        timestamp: Optional[str] = None,
    ) -> Optional[TradeRecord]:
        """
        Apply a fill. Opposite-side fills close (or flip) the open position and
        return a TradeRecord for the closed portion.
        """
        if not fill.success or fill.executed_amount <= 0:
            return None

        self.trade_history.append(fill)
        self.equity -= fill.fee
        self.fees_paid += fill.fee
        symbol = fill.symbol
        record: Optional[TradeRecord] = None
        existing = self.positions.get(symbol)

        if existing is None:
            self.positions[symbol] = Position(
                symbol, fill.side, fill.executed_amount, fill.executed_price, fill.executed_price,
                stop_loss, take_profit, opened_at=timestamp,
            )
        elif existing.side == fill.side:
            total = existing.amount + fill.executed_amount
            existing.entry_price = (existing.entry_price * existing.amount + fill.executed_price * fill.executed_amount) / total
            existing.amount = total
            if stop_loss:
                existing.stop_loss = stop_loss
            if take_profit:
                existing.take_profit = take_profit
        else:
            closed_amount = min(existing.amount, fill.executed_amount)
            direction = 1.0 if existing.side == OrderSide.BUY else -1.0
            pnl = (fill.executed_price - existing.entry_price) * closed_amount * direction
            equity_before = self.equity
            self.equity += pnl
            self.realized_pnl += pnl
            record = TradeRecord(
                symbol=symbol,
                side=existing.side,
                amount=closed_amount,
                entry_price=existing.entry_price,
                exit_price=fill.executed_price,
                pnl=pnl,
                pnl_pct_equity=(pnl - fill.fee) / equity_before if equity_before > 0 else 0.0,
                fee=fill.fee,
                reason=reason,
                closed_at=timestamp,
            )
            self.closed_trades.append(record)
            remaining = existing.amount - closed_amount
            if remaining > 1e-12:
                existing.amount = remaining
            else:
                del self.positions[symbol]
                flip = fill.executed_amount - closed_amount
                if flip > 1e-12:
                    self.positions[symbol] = Position(
                        symbol, fill.side, flip, fill.executed_price, fill.executed_price,
                        stop_loss, take_profit, opened_at=timestamp,
                    )

        self.mark_to_market(symbol, fill.executed_price)
        return record

    # ------------------------------------------------------------ snapshots
    def snapshot(self) -> Dict[str, Any]:
        return {
            "pod_id": self.pod_id,
            "initial_equity": self.initial_equity,
            "equity": self.equity,
            "peak_equity": self.peak_equity,
            "realized_pnl": self.realized_pnl,
            "fees_paid": self.fees_paid,
            "equity_curve_tail": self.equity_curve[-50:],
            "positions": {sym: pos.to_dict() for sym, pos in self.positions.items()},
        }

    def restore(self, snapshot: Dict[str, Any]) -> None:
        self.equity = float(snapshot.get("equity", self.equity))
        self.peak_equity = float(snapshot.get("peak_equity", self.peak_equity))
        self.realized_pnl = float(snapshot.get("realized_pnl", self.realized_pnl))
        self.fees_paid = float(snapshot.get("fees_paid", self.fees_paid))
        tail = snapshot.get("equity_curve_tail")
        if tail:
            self.equity_curve = [float(x) for x in tail]
        self.positions = {}
        for sym, p in (snapshot.get("positions") or {}).items():
            self.positions[sym] = Position(
                symbol=sym,
                side=OrderSide[p["side"]],
                amount=float(p["amount"]),
                entry_price=float(p["entry_price"]),
                current_price=float(p["current_price"]),
                stop_loss=float(p.get("stop_loss", 0.0)),
                take_profit=float(p.get("take_profit", 0.0)),
                unrealized_pnl=float(p.get("unrealized_pnl", 0.0)),
                opened_at=p.get("opened_at"),
            )

    def returns_series(self) -> pd.Series:
        curve = pd.Series(self.equity_curve, dtype=float)
        return curve.pct_change().dropna()
