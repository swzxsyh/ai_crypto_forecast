"""Binance 真实/测试网交易执行。"""

from __future__ import annotations

from typing import Any

from crypto_predictor.broker.models import OrderRequest, OrderResult
from crypto_predictor.config import (
    BINANCE_API_KEY,
    BINANCE_MARKET_TYPE,
    BINANCE_SANDBOX,
    BINANCE_SECRET,
    ENABLE_LIVE_TRADING,
    LIVE_CONFIRM_TEXT,
    PLACE_BRACKET_ORDERS,
    POSITION_SIDE_MODE,
)


def execute_binance_order(request: OrderRequest, confirm: str | None = None) -> OrderResult:
    """通过 ccxt 向 Binance 发送真实或测试网订单。"""

    if request.mode != "live":
        raise ValueError("Binance broker 只接受 live 模式请求")

    if not ENABLE_LIVE_TRADING:
        raise RuntimeError("ENABLE_LIVE_TRADING 未开启，拒绝真实下单")

    if confirm != LIVE_CONFIRM_TEXT:
        raise RuntimeError("真实下单确认文本不匹配，拒绝执行")

    if not BINANCE_API_KEY or not BINANCE_SECRET:
        raise RuntimeError("缺少 BINANCE_API_KEY 或 BINANCE_SECRET")

    try:
        import ccxt
    except ImportError as exc:
        raise RuntimeError("缺少 ccxt SDK，请先执行：pip install ccxt") from exc

    exchange = ccxt.binance(
        {
            "apiKey": BINANCE_API_KEY,
            "secret": BINANCE_SECRET,
            "enableRateLimit": True,
            "options": {
                "defaultType": BINANCE_MARKET_TYPE,
            },
        }
    )

    if BINANCE_SANDBOX:
        exchange.set_sandbox_mode(True)

    exchange.load_markets()
    exchange.set_leverage(request.leverage, request.symbol)

    amount = float(exchange.amount_to_precision(request.symbol, request.amount))
    entry_side = "buy" if request.position_side == "LONG" else "sell"
    exit_side = "sell" if request.position_side == "LONG" else "buy"
    params = build_position_params(request.position_side)

    entry_order = exchange.create_order(
        symbol=request.symbol,
        type="market",
        side=entry_side,
        amount=amount,
        price=None,
        params={**params, "newOrderRespType": "RESULT"},
    )

    take_profit_order: dict[str, Any] | None = None
    stop_loss_order: dict[str, Any] | None = None

    if PLACE_BRACKET_ORDERS:
        take_profit_order = exchange.create_order(
            symbol=request.symbol,
            type="TAKE_PROFIT_MARKET",
            side=exit_side,
            amount=amount,
            price=None,
            params={
                **params,
                "stopPrice": float(exchange.price_to_precision(request.symbol, request.take_profit_price)),
                "reduceOnly": True,
                "workingType": "MARK_PRICE",
            },
        )
        stop_loss_order = exchange.create_order(
            symbol=request.symbol,
            type="STOP_MARKET",
            side=exit_side,
            amount=amount,
            price=None,
            params={
                **params,
                "stopPrice": float(exchange.price_to_precision(request.symbol, request.stop_loss_price)),
                "reduceOnly": True,
                "workingType": "MARK_PRICE",
            },
        )

    return OrderResult(
        mode="live",
        status=str(entry_order.get("status", "submitted")),
        exchange="binance",
        symbol=request.symbol,
        side=entry_side,
        amount=amount,
        leverage=request.leverage,
        entry_order_id=str(entry_order.get("id") or entry_order.get("orderId") or ""),
        take_profit_order_id=extract_order_id(take_profit_order),
        stop_loss_order_id=extract_order_id(stop_loss_order),
        message="Binance 订单已提交。",
        raw_response={
            "sandbox": BINANCE_SANDBOX,
            "entry_order": entry_order,
            "take_profit_order": take_profit_order,
            "stop_loss_order": stop_loss_order,
        },
    )


def build_position_params(position_side: str) -> dict[str, Any]:
    """根据账户持仓模式构建下单参数。"""

    if POSITION_SIDE_MODE == "hedge":
        return {"positionSide": position_side}
    return {}


def extract_order_id(order: dict[str, Any] | None) -> str | None:
    """从 ccxt 返回中提取订单 ID。"""

    if not order:
        return None
    return str(order.get("id") or order.get("orderId") or "")
