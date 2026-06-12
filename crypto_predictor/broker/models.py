"""Trading execution layer data structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


ExecutionMode = Literal["paper", "live"]
CloseReason = Literal["expired", "manual", "take_profit", "stop_loss", "error"]


@dataclass(frozen=True)
class OrderRequest:
    """Order request built from a prediction record."""

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
    """Entry order execution result."""

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


@dataclass(frozen=True)
class CloseOrderRequest:
    """Close request for a recorded trade order."""

    trade_order_id: int
    prediction_id: int
    symbol: str
    position_side: str
    entry_side: str
    amount: float
    mode: ExecutionMode
    reason: CloseReason = "expired"


@dataclass(frozen=True)
class CloseOrderResult:
    """Position close execution result."""

    mode: ExecutionMode
    status: str
    exchange: str
    symbol: str
    side: str
    amount: float
    close_order_id: str | None
    exit_price: float | None
    message: str
    raw_response: dict[str, Any]
