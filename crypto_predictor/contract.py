"""模拟合约方案校验与盈亏计算。

这里只做线性 USDT 合约的简化估算：
    名义仓位 = 保证金 * 杠杆
    数量 = 名义仓位 / 入场价
    多单盈亏 = 数量 * (出场价 - 入场价)
    空单盈亏 = 数量 * (入场价 - 出场价)

暂不计手续费、资金费率、滑点和强平价格。
"""

from __future__ import annotations

from dataclasses import replace

from crypto_predictor.config import (
    CONTRACT_MAX_LEVERAGE,
    CONTRACT_MAX_MARGIN,
    CONTRACT_MIN_MARGIN,
    RISK_MAX_MARGIN_PER_TRADE,
)
from crypto_predictor.models import Prediction


def enrich_contract_metrics(prediction: Prediction, entry_price: float) -> Prediction:
    """校验模拟合约参数，并补齐系统计算字段。"""

    if entry_price <= 0:
        raise ValueError(f"entry_price 必须大于 0: {entry_price}")

    position_side = normalize_position_side(prediction)

    if position_side == "NO_TRADE":
        return replace(
            prediction,
            position_side="NO_TRADE",
            margin_amount=0.0,
            leverage=0,
            entry_price=entry_price,
            take_profit_price=entry_price,
            stop_loss_price=entry_price,
            notional_value=0.0,
            expected_profit=0.0,
            expected_loss=0.0,
            risk_reward_ratio=None,
        )

    margin_amount = clamp(float(prediction.margin_amount), CONTRACT_MIN_MARGIN, effective_max_margin())
    leverage = max(1, min(int(prediction.leverage), CONTRACT_MAX_LEVERAGE))
    take_profit_price = float(prediction.take_profit_price)
    stop_loss_price = float(prediction.stop_loss_price)

    validate_exit_prices(position_side, entry_price, take_profit_price, stop_loss_price)

    notional_value = margin_amount * leverage
    quantity = notional_value / entry_price

    if position_side == "LONG":
        expected_profit = quantity * (take_profit_price - entry_price)
        expected_loss = quantity * (entry_price - stop_loss_price)
    else:
        expected_profit = quantity * (entry_price - take_profit_price)
        expected_loss = quantity * (stop_loss_price - entry_price)

    expected_profit = max(0.0, expected_profit)
    expected_loss = max(0.0, expected_loss)
    risk_reward_ratio = (expected_profit / expected_loss) if expected_loss > 0 else None

    return replace(
        prediction,
        position_side=position_side,
        margin_amount=round(margin_amount, 2),
        leverage=leverage,
        entry_price=round(entry_price, 8),
        take_profit_price=round(take_profit_price, 8),
        stop_loss_price=round(stop_loss_price, 8),
        notional_value=round(notional_value, 2),
        expected_profit=round(expected_profit, 2),
        expected_loss=round(expected_loss, 2),
        risk_reward_ratio=round(risk_reward_ratio, 4) if risk_reward_ratio is not None else None,
    )


def normalize_position_side(prediction: Prediction) -> str:
    """让方向和合约方向保持一致。"""

    if prediction.direction == "SIDEWAYS" or prediction.confidence < 40:
        return "NO_TRADE"
    if prediction.direction == "UP":
        return "LONG"
    if prediction.direction == "DOWN":
        return "SHORT"
    return prediction.position_side


def validate_exit_prices(
    position_side: str,
    entry_price: float,
    take_profit_price: float,
    stop_loss_price: float,
) -> None:
    """校验止盈止损方向是否合理。"""

    if take_profit_price <= 0 or stop_loss_price <= 0:
        raise ValueError("止盈价和止损价必须大于 0")

    if position_side == "LONG":
        if take_profit_price <= entry_price:
            raise ValueError("LONG 的止盈价必须高于入场价")
        if stop_loss_price >= entry_price:
            raise ValueError("LONG 的止损价必须低于入场价")
        return

    if position_side == "SHORT":
        if take_profit_price >= entry_price:
            raise ValueError("SHORT 的止盈价必须低于入场价")
        if stop_loss_price <= entry_price:
            raise ValueError("SHORT 的止损价必须高于入场价")
        return

    raise ValueError(f"不支持的 position_side: {position_side}")


def clamp(value: float, min_value: float, max_value: float) -> float:
    """限制数值范围。"""

    return max(min_value, min(value, max_value))


def effective_max_margin() -> float:
    return max(CONTRACT_MIN_MARGIN, min(CONTRACT_MAX_MARGIN, RISK_MAX_MARGIN_PER_TRADE))
