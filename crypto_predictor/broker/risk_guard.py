"""下单前风控拦截。"""

from __future__ import annotations

from crypto_predictor.config import RISK_ALLOWED_SYMBOLS, RISK_MAX_LEVERAGE, RISK_MAX_MARGIN_PER_TRADE
from crypto_predictor.broker.models import OrderRequest


def validate_order_request(request: OrderRequest, max_margin_override: float | None = None) -> None:
    """校验是否允许执行该模拟/真实订单。"""

    if request.symbol not in RISK_ALLOWED_SYMBOLS:
        raise ValueError(f"{request.symbol} 不在风控允许交易对列表中")

    if request.position_side not in {"LONG", "SHORT"}:
        raise ValueError(f"position_side={request.position_side}，不允许下单")

    if request.margin_amount <= 0:
        raise ValueError("保证金必须大于 0")

    effective_max_margin = max_margin_override if max_margin_override is not None else RISK_MAX_MARGIN_PER_TRADE
    if request.margin_amount > effective_max_margin:
        raise ValueError(
            f"保证金 {request.margin_amount} 超过单笔上限 {effective_max_margin}"
        )

    if request.leverage <= 0:
        raise ValueError("杠杆必须大于 0")

    if request.leverage > RISK_MAX_LEVERAGE:
        raise ValueError(f"杠杆 {request.leverage} 超过风控上限 {RISK_MAX_LEVERAGE}")

    if request.entry_price <= 0 or request.amount <= 0 or request.notional_value <= 0:
        raise ValueError("入场价、数量、名义仓位都必须大于 0")

    if request.position_side == "LONG":
        if request.take_profit_price <= request.entry_price:
            raise ValueError("LONG 止盈价必须高于入场价")
        if request.stop_loss_price >= request.entry_price:
            raise ValueError("LONG 止损价必须低于入场价")

    if request.position_side == "SHORT":
        if request.take_profit_price >= request.entry_price:
            raise ValueError("SHORT 止盈价必须低于入场价")
        if request.stop_loss_price <= request.entry_price:
            raise ValueError("SHORT 止损价必须高于入场价")
