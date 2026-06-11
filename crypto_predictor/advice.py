"""建议生成模块。"""

from __future__ import annotations

from typing import Any

from crypto_predictor.config import (
    CONTRACT_DEFAULT_LEVERAGE,
    CONTRACT_MAX_LEVERAGE,
    CONTRACT_MAX_MARGIN,
    CONTRACT_MIN_MARGIN,
    RISK_MAX_LEVERAGE,
    RISK_MAX_MARGIN_PER_TRADE,
)


def build_advice_from_prediction(prediction_row: Any, principal: float) -> dict[str, Any]:
    """根据最近预测给出建议参数。"""

    if principal <= 0:
        raise ValueError("本金必须大于 0")

    symbol = str(prediction_row["symbol"])
    direction = str(prediction_row["prediction_direction"])
    position_side = str(prediction_row["position_side"])
    timeframe = str(prediction_row["timeframe"])
    entry_price = float(prediction_row["entry_price"] or prediction_row["current_price"] or 0)
    take_profit_price = float(prediction_row["take_profit_price"] or 0)
    stop_loss_price = float(prediction_row["stop_loss_price"] or 0)

    if entry_price <= 0:
        raise ValueError(f"{symbol} 入场价格异常")

    if position_side not in {"LONG", "SHORT"}:
        return {
            "symbol": symbol,
            "principal": principal,
            "prediction_id": int(prediction_row["id"]),
            "timeframe": timeframe,
            "expires_at": prediction_row["expires_at"],
            "direction": direction,
            "suggestion_side": "WAIT",
            "side_label": "观望",
            "leverage": 0,
            "margin_amount": 0.0,
            "entry_price": entry_price,
            "take_profit_price": take_profit_price,
            "stop_loss_price": stop_loss_price,
            "notional_value": 0.0,
            "expected_profit": 0.0,
            "expected_loss": 0.0,
            "confidence": int(prediction_row["confidence"] or 0),
            "reason": "当前信号偏震荡或不建议开仓。",
        }

    leverage_raw = int(prediction_row["leverage"] or CONTRACT_DEFAULT_LEVERAGE)
    leverage = min(max(1, leverage_raw), RISK_MAX_LEVERAGE, CONTRACT_MAX_LEVERAGE)

    max_margin = min(principal, RISK_MAX_MARGIN_PER_TRADE, CONTRACT_MAX_MARGIN)
    base_margin = max(principal * 0.1, CONTRACT_MIN_MARGIN)
    margin_amount = min(max_margin, base_margin)
    margin_amount = max(0.0, margin_amount)

    notional_value = margin_amount * leverage

    if position_side == "LONG":
        expected_profit = max(0.0, (take_profit_price - entry_price) / entry_price * notional_value)
        expected_loss = max(0.0, (entry_price - stop_loss_price) / entry_price * notional_value)
        side_label = "看多"
    else:
        expected_profit = max(0.0, (entry_price - take_profit_price) / entry_price * notional_value)
        expected_loss = max(0.0, (stop_loss_price - entry_price) / entry_price * notional_value)
        side_label = "看空"

    return {
        "symbol": symbol,
        "principal": principal,
        "prediction_id": int(prediction_row["id"]),
        "timeframe": timeframe,
        "expires_at": prediction_row["expires_at"],
        "direction": direction,
        "suggestion_side": position_side,
        "side_label": side_label,
        "leverage": leverage,
        "margin_amount": margin_amount,
        "entry_price": entry_price,
        "take_profit_price": take_profit_price,
        "stop_loss_price": stop_loss_price,
        "notional_value": notional_value,
        "expected_profit": expected_profit,
        "expected_loss": expected_loss,
        "confidence": int(prediction_row["confidence"] or 0),
        "reason": "建议仅供参考，请自行评估风险。",
    }
