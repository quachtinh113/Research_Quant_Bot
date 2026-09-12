"""
CCXT unified execution gateway and order lifecycle management.
"""

from .ccxt_gateway import CCXTExecutionGateway, ExecutionResult, MarketRules, NormalizedOrder
from .order_manager import OrderManager, Position, TradeRecord

__all__ = [
    "CCXTExecutionGateway",
    "ExecutionResult",
    "MarketRules",
    "NormalizedOrder",
    "OrderManager",
    "Position",
    "TradeRecord",
]
