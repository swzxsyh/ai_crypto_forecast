"""Binance live/testnet trading execution."""

from __future__ import annotations

from typing import Any

from crypto_predictor.broker.models import CloseOrderRequest, CloseOrderResult, OrderRequest, OrderResult
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
    """Send a live/testnet entry order to Binance through ccxt."""

    if request.mode != "live":
        raise ValueError("Binance broker only accepts live mode requests")

    if not ENABLE_LIVE_TRADING:
        raise RuntimeError("ENABLE_LIVE_TRADING is disabled; refusing live order")

    if confirm != LIVE_CONFIRM_TEXT:
        raise RuntimeError("Live trading confirmation text does not match; refusing order")

    exchange = build_binance_exchange()
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
        entry_order_id=extract_order_id(entry_order),
        take_profit_order_id=extract_order_id(take_profit_order),
        stop_loss_order_id=extract_order_id(stop_loss_order),
        message="Binance entry order submitted.",
        raw_response={
            "sandbox": BINANCE_SANDBOX,
            "entry_order": entry_order,
            "take_profit_order": take_profit_order,
            "stop_loss_order": stop_loss_order,
        },
    )


def close_binance_position(request: CloseOrderRequest) -> CloseOrderResult:
    """Close a recorded Binance position with a reduce-only market order."""

    if request.mode != "live":
        raise ValueError("Binance broker only closes live mode requests")

    if not ENABLE_LIVE_TRADING:
        raise RuntimeError("ENABLE_LIVE_TRADING is disabled; refusing live close")

    exchange = build_binance_exchange()
    amount = float(exchange.amount_to_precision(request.symbol, request.amount))
    close_side = "sell" if request.entry_side == "buy" else "buy"
    params = {
        **build_position_params(request.position_side),
        "reduceOnly": True,
        "newOrderRespType": "RESULT",
    }

    close_order = exchange.create_order(
        symbol=request.symbol,
        type="market",
        side=close_side,
        amount=amount,
        price=None,
        params=params,
    )

    return CloseOrderResult(
        mode="live",
        status=str(close_order.get("status", "submitted")),
        exchange="binance",
        symbol=request.symbol,
        side=close_side,
        amount=amount,
        close_order_id=extract_order_id(close_order),
        exit_price=extract_average_price(close_order),
        message="Binance reduce-only close order submitted.",
        raw_response={
            "sandbox": BINANCE_SANDBOX,
            "reason": request.reason,
            "close_order": close_order,
        },
    )


def build_binance_exchange():
    if not BINANCE_API_KEY or not BINANCE_SECRET:
        raise RuntimeError("Missing BINANCE_API_KEY or BINANCE_SECRET")

    try:
        import ccxt
    except ImportError as exc:
        raise RuntimeError("Missing ccxt SDK. Install with: pip install ccxt") from exc

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
    return exchange


def build_position_params(position_side: str) -> dict[str, Any]:
    """Build params for one-way or hedge position mode."""

    if POSITION_SIDE_MODE == "hedge":
        return {"positionSide": position_side}
    return {}


def extract_order_id(order: dict[str, Any] | None) -> str | None:
    if not order:
        return None
    return str(order.get("id") or order.get("orderId") or "")


def extract_average_price(order: dict[str, Any]) -> float | None:
    for key in ("average", "avgPrice", "price"):
        value = order.get(key)
        if value not in (None, "", 0, "0"):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    info = order.get("info") or {}
    for key in ("avgPrice", "price"):
        value = info.get(key)
        if value not in (None, "", 0, "0"):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None
