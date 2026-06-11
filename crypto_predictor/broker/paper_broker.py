"""纸面模拟交易执行。"""

from __future__ import annotations

from crypto_predictor.broker.models import OrderRequest, OrderResult


def execute_paper_order(request: OrderRequest) -> OrderResult:
    """只记录模拟成交，不访问交易所。"""

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
        message="纸面模拟完成，没有发送真实订单。",
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
