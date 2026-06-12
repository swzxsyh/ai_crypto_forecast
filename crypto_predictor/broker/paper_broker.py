"""Paper trading execution."""

from __future__ import annotations

from crypto_predictor.broker.models import CloseOrderRequest, CloseOrderResult, OrderRequest, OrderResult


def execute_paper_order(request: OrderRequest) -> OrderResult:
    """Record a simulated entry order without touching an exchange."""

    side = "buy" if request.position_side == "LONG" else "sell"
    return OrderResult(
        mode="paper",
        status="simulated",
        exchange="paper",
        symbol=request.symbol,
        side=side,
        amount=request.amount,
        leverage=request.leverage,
        entry_order_id=f"paper-entry-{request.prediction_id}",
        take_profit_order_id=f"paper-tp-{request.prediction_id}",
        stop_loss_order_id=f"paper-sl-{request.prediction_id}",
        message="Paper order recorded; no real order was sent.",
        raw_response={
            "prediction_id": request.prediction_id,
            "position_side": request.position_side,
            "margin_amount": request.margin_amount,
            "notional_value": request.notional_value,
            "entry_price": request.entry_price,
            "take_profit_price": request.take_profit_price,
            "stop_loss_price": request.stop_loss_price,
        },
    )


def close_paper_order(request: CloseOrderRequest, exit_price: float | None = None) -> CloseOrderResult:
    """Record a simulated close order."""

    side = "sell" if request.entry_side == "buy" else "buy"
    return CloseOrderResult(
        mode="paper",
        status="closed",
        exchange="paper",
        symbol=request.symbol,
        side=side,
        amount=request.amount,
        close_order_id=f"paper-close-{request.trade_order_id}",
        exit_price=exit_price,
        message="Paper position closed by lifecycle manager.",
        raw_response={
            "trade_order_id": request.trade_order_id,
            "prediction_id": request.prediction_id,
            "position_side": request.position_side,
            "reason": request.reason,
            "exit_price": exit_price,
        },
    )
