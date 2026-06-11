"""交易执行层数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


ExecutionMode = Literal["paper", "live"]


@dataclass(frozen=True)
class OrderRequest:
    """从预测记录转换而来的下单请求。"""

    prediction_id: int
    symbol: str
    position_side: str
    margin_amount: float
    leverage: int
    entry_price: float
    take_profit_price: float
    stop_loss_price: float
    notional_value: float
    amount: float
    mode: ExecutionMode


@dataclass(frozen=True)
class OrderResult:
    """执行结果。"""

    mode: ExecutionMode
    status: str
    exchange: str
    symbol: str
    side: str
    amount: float
    leverage: int
    entry_order_id: str | None
    take_profit_order_id: str | None
    stop_loss_order_id: str | None
    message: str
    raw_response: dict[str, Any]
