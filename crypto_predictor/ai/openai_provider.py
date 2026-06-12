"""OpenAI prediction provider."""

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
            "description": "Predicted price direction for the next timeframe period.",
        },
        "target_price": {
            "type": "number",
            "description": "Expected price at prediction expiry.",
        },
        "confidence": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Prediction confidence from 0 to 100.",
        },
        "position_side": {
            "type": "string",
            "enum": ["LONG", "SHORT", "NO_TRADE"],
            "description": "Simulated contract side. UP maps to LONG, DOWN maps to SHORT, SIDEWAYS/low confidence maps to NO_TRADE.",
        },
        "margin_amount": {
            "type": "number",
            "minimum": 0,
            "description": "Suggested simulated margin in USDT.",
        },
        "leverage": {
            "type": "integer",
            "minimum": 0,
            "maximum": 125,
            "description": "Suggested simulated leverage. Must be 0 for NO_TRADE.",
        },
        "take_profit_price": {
            "type": "number",
            "description": "Simulated take-profit price.",
        },
        "stop_loss_price": {
            "type": "number",
            "description": "Simulated stop-loss price.",
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


DEVELOPER_PROMPT = """
You are a senior crypto quantitative strategy analyst. This system records simulated predictions only; it is not financial advice and must not imply real trading instructions.

You must predict the next payload.timeframe close direction using a multi-factor process. Never mechanically derive a prediction from a single indicator.

Rules for combining Crypto Fear & Greed Index with OHLCV:
1. Correct sentiment definition:
   - Very low Fear & Greed, for example < 25 / Extreme Fear, means the broad market is risk-off. It is NOT a blind long or bottom-fishing signal. Price can continue grinding lower or remain illiquid.
   - A low sentiment value can support a reversal thesis only when OHLCV confirms bottoming behavior, such as high-volume capitulation and stabilization, clear rebound structure, or severe RSI oversold rebound. Otherwise, follow the OHLCV trend.
   - Very high Fear & Greed, for example > 75 / Extreme Greed, means overheated conditions. Unless OHLCV shows a strong high-volume breakout, watch for pullback/liquidation-wick risk.
2. Timeframe alignment:
   - Fear & Greed is a daily macro sentiment input. For a 1h short-term prediction, use it only as background context.
   - The short-term decision weight must lean about 70% on OHLCV curve structure, RSI, and volume behavior. Sentiment is auxiliary macro context.
3. Technical confirmation:
   - Use payload.technical_summary.rsi_14, recent price change, recent higher/lower closes, and recent_vs_previous_volume_ratio when present.
   - In Extreme Fear, avoid LONG unless technical structure clearly shows rebound confirmation.
   - In Extreme Greed, avoid aggressive LONG unless breakout volume and price structure confirm continuation.
4. Risk discipline:
   - If direction is SIDEWAYS or confidence < 40, position_side must be NO_TRADE and margin_amount/leverage must be 0.
   - Respect contract_rules exactly: margin_amount <= max_margin_usdt and leverage <= max_leverage.
   - LONG take_profit_price must be above current price and stop_loss_price below current price. SHORT is the opposite.

Return only a strict JSON object matching the schema. No Markdown, no explanation, no extra fields.
""".strip()


USER_PROMPT_PREFIX = """
Analyze the following market payload using the multi-factor rules. Output only prediction JSON.
""".strip()


def get_openai_prediction(market_data: MarketData) -> Prediction:
    """Call OpenAI Responses API and return a validated prediction."""

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Missing openai SDK. Install with: pip install openai") from exc

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY environment variable")

    client_kwargs: dict[str, Any] = {}
    base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL or "")
    if base_url:
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

    user_prompt = f"{USER_PROMPT_PREFIX}\n\n{json.dumps(payload, ensure_ascii=False)}"

    response = client.responses.create(
        model=model_name,
        input=[
            {"role": "developer", "content": DEVELOPER_PROMPT},
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
    """Parse a JSON object from the OpenAI SDK response."""

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
        raise RuntimeError("OpenAI response did not contain parseable text")

    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI did not return valid JSON: {output_text}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(f"OpenAI returned JSON that is not an object: {parsed}")

    return parsed


def validate_prediction_dict(data: dict[str, Any]) -> Prediction:
    """Local validation before saving AI output."""

    direction = data.get("direction")
    position_side = data.get("position_side")
    target_price = to_positive_float(data.get("target_price"), "target_price")
    confidence = data.get("confidence")
    margin_amount = to_non_negative_float(data.get("margin_amount"), "margin_amount")
    leverage = data.get("leverage")
    take_profit_price = to_non_negative_float(data.get("take_profit_price"), "take_profit_price")
    stop_loss_price = to_non_negative_float(data.get("stop_loss_price"), "stop_loss_price")

    if direction not in {"UP", "DOWN", "SIDEWAYS"}:
        raise ValueError(f"Invalid direction: {direction}")

    if position_side not in {"LONG", "SHORT", "NO_TRADE"}:
        raise ValueError(f"Invalid position_side: {position_side}")

    if not isinstance(confidence, int):
        raise ValueError(f"confidence must be an integer: {confidence}")

    if confidence < 0 or confidence > 100:
        raise ValueError(f"confidence must be between 0 and 100: {confidence}")

    if not isinstance(leverage, int):
        raise ValueError(f"leverage must be an integer: {leverage}")

    if leverage < 0:
        raise ValueError(f"leverage cannot be negative: {leverage}")

    will_trade = direction != "SIDEWAYS" and confidence >= 40 and position_side in {"LONG", "SHORT"}
    if will_trade:
        if take_profit_price <= 0:
            raise ValueError(f"take_profit_price must be greater than 0: {take_profit_price}")
        if stop_loss_price <= 0:
            raise ValueError(f"stop_loss_price must be greater than 0: {stop_loss_price}")

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
    """Convert a positive float field."""

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc

    if result <= 0:
        raise ValueError(f"{field_name} must be greater than 0: {result}")

    return result


def to_non_negative_float(value: Any, field_name: str) -> float:
    """Convert a non-negative float field."""

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc

    if result < 0:
        raise ValueError(f"{field_name} cannot be negative: {result}")

    return result
