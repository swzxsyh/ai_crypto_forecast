"""OpenAI 预测实现。"""

from __future__ import annotations

import json
import os
from typing import Any

from crypto_predictor.config import (
    CONTRACT_DEFAULT_LEVERAGE,
    CONTRACT_DEFAULT_MARGIN,
    CONTRACT_MAX_LEVERAGE,
    CONTRACT_MAX_MARGIN,
    CONTRACT_MIN_MARGIN,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    RISK_MAX_MARGIN_PER_TRADE,
)
from crypto_predictor.market_data import compact_market_data_for_prompt
from crypto_predictor.models import MarketData, Prediction


PREDICTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "direction": {
            "type": "string",
            "enum": ["UP", "DOWN", "SIDEWAYS"],
            "description": "预测下一个周期的价格方向",
        },
        "target_price": {
            "type": "number",
            "description": "预测到期时的目标价格",
        },
        "confidence": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "预测置信度，0 到 100 的整数",
        },
        "position_side": {
            "type": "string",
            "enum": ["LONG", "SHORT", "NO_TRADE"],
            "description": "模拟合约方向，UP 对应 LONG，DOWN 对应 SHORT，震荡或低置信度为 NO_TRADE",
        },
        "margin_amount": {
            "type": "number",
            "minimum": 0,
            "description": "建议使用的模拟保证金，单位 USDT",
        },
        "leverage": {
            "type": "integer",
            "minimum": 0,
            "maximum": 125,
            "description": "建议模拟杠杆倍数；NO_TRADE 时为 0",
        },
        "take_profit_price": {
            "type": "number",
            "description": "模拟止盈价格",
        },
        "stop_loss_price": {
            "type": "number",
            "description": "模拟止损价格",
        },
    },
    "required": [
        "direction",
        "target_price",
        "confidence",
        "position_side",
        "margin_amount",
        "leverage",
        "take_profit_price",
        "stop_loss_price",
    ],
    "additionalProperties": False,
}


def get_openai_prediction(market_data: MarketData) -> Prediction:
    """调用 OpenAI Responses API 获取严格 JSON 预测。"""

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("缺少 openai SDK，请先执行：pip install openai") from exc

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("缺少 OPENAI_API_KEY 环境变量，无法调用 OpenAI API。")

    client_kwargs: dict[str, Any] = {}
    base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL or "")
    if base_url:
        # 兼容中转站、私有网关或 OpenAI-compatible API；通常应以 /v1 结尾。
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)
    model_name = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    payload = compact_market_data_for_prompt(market_data)
    effective_max_margin = max(CONTRACT_MIN_MARGIN, min(CONTRACT_MAX_MARGIN, RISK_MAX_MARGIN_PER_TRADE))
    payload["contract_rules"] = {
        "default_margin_usdt": min(CONTRACT_DEFAULT_MARGIN, effective_max_margin),
        "min_margin_usdt": CONTRACT_MIN_MARGIN,
        "max_margin_usdt": effective_max_margin,
        "default_leverage": CONTRACT_DEFAULT_LEVERAGE,
        "max_leverage": CONTRACT_MAX_LEVERAGE,
        "no_trade_when_sideways_or_low_confidence": True,
    }

    developer_prompt = (
        "你是一个谨慎的量化研究助手，只做模拟预测，不给出投资建议。"
        "请基于用户提供的 OHLCV 数据，预测下一个 timeframe 周期结束时的价格方向，"
        "并给出模拟 USDT 线性合约方案。"
        "必须严格遵守 contract_rules：保证金不能超过 max_margin_usdt，杠杆不能超过 max_leverage。"
        "如果方向为 SIDEWAYS 或置信度低于 40，position_side 必须为 NO_TRADE，margin_amount 和 leverage 必须为 0。"
        "LONG 的止盈价应高于当前价、止损价应低于当前价；SHORT 相反。"
        "必须输出严格符合 JSON Schema 的对象，不要输出解释、Markdown 或额外字段。"
    )
    user_prompt = (
        "请根据以下市场数据做一次模拟预测。"
        "注意：这不是交易指令，只用于记录和事后验证。\n\n"
        "Use payload.sentiment.crypto_fear_greed_index as an auxiliary sentiment input when present.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

    response = client.responses.create(
        model=model_name,
        input=[
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "crypto_contract_prediction",
                "schema": PREDICTION_SCHEMA,
                "strict": True,
            },
            "verbosity": "low",
        },
    )

    prediction_dict = parse_openai_json_response(response)
    return validate_prediction_dict(prediction_dict)


def parse_openai_json_response(response: Any) -> dict[str, Any]:
    """从 OpenAI SDK 响应中解析 JSON。"""

    output_text = getattr(response, "output_text", None)

    if not output_text:
        texts: list[str] = []
        for output_item in getattr(response, "output", []) or []:
            for content_item in getattr(output_item, "content", []) or []:
                text = getattr(content_item, "text", None)
                if text:
                    texts.append(text)
        output_text = "\n".join(texts)

    if not output_text:
        raise RuntimeError("OpenAI 响应中没有可解析的文本内容。")

    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI 未返回合法 JSON：{output_text}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(f"OpenAI 返回的 JSON 不是对象：{parsed}")

    return parsed


def validate_prediction_dict(data: dict[str, Any]) -> Prediction:
    """对 AI 返回值做本地二次校验，防止脏数据进入数据库。"""

    direction = data.get("direction")
    position_side = data.get("position_side")
    target_price = to_positive_float(data.get("target_price"), "target_price")
    confidence = data.get("confidence")
    margin_amount = to_non_negative_float(data.get("margin_amount"), "margin_amount")
    leverage = data.get("leverage")
    take_profit_price = to_non_negative_float(data.get("take_profit_price"), "take_profit_price")
    stop_loss_price = to_non_negative_float(data.get("stop_loss_price"), "stop_loss_price")

    if direction not in {"UP", "DOWN", "SIDEWAYS"}:
        raise ValueError(f"非法 direction: {direction}")

    if position_side not in {"LONG", "SHORT", "NO_TRADE"}:
        raise ValueError(f"非法 position_side: {position_side}")

    if not isinstance(confidence, int):
        raise ValueError(f"confidence 必须是整数: {confidence}")

    if confidence < 0 or confidence > 100:
        raise ValueError(f"confidence 必须在 0-100 之间: {confidence}")

    if not isinstance(leverage, int):
        raise ValueError(f"leverage 必须是整数: {leverage}")

    if leverage < 0:
        raise ValueError(f"leverage 不能小于 0: {leverage}")

    will_trade = direction != "SIDEWAYS" and confidence >= 40 and position_side in {"LONG", "SHORT"}
    if will_trade:
        if take_profit_price <= 0:
            raise ValueError(f"take_profit_price 蹇呴』澶т簬 0: {take_profit_price}")
        if stop_loss_price <= 0:
            raise ValueError(f"stop_loss_price 蹇呴』澶т簬 0: {stop_loss_price}")

    return Prediction(
        direction=direction,
        target_price=target_price,
        confidence=confidence,
        position_side=position_side,
        margin_amount=margin_amount,
        leverage=leverage,
        take_profit_price=take_profit_price,
        stop_loss_price=stop_loss_price,
    )


def to_positive_float(value: Any, field_name: str) -> float:
    """转换正数浮点字段。"""

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"非法 {field_name}: {value}") from exc

    if result <= 0:
        raise ValueError(f"{field_name} 必须大于 0: {result}")

    return result


def to_non_negative_float(value: Any, field_name: str) -> float:
    """转换非负浮点字段。"""

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"非法 {field_name}: {value}") from exc

    if result < 0:
        raise ValueError(f"{field_name} 不能小于 0: {result}")

    return result
