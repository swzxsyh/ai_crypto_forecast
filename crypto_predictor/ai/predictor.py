"""AI 预测统一入口。"""

from __future__ import annotations

from crypto_predictor.ai.openai_provider import get_openai_prediction
from crypto_predictor.models import MarketData, ModelType, Prediction


def get_ai_prediction(market_data: MarketData, model_type: ModelType = "openai") -> Prediction:
    """根据 model_type 分发到不同 AI 提供商。"""

    if model_type == "openai":
        return get_openai_prediction(market_data)

    if model_type == "anthropic":
        # 预留扩展点：未来实现 get_anthropic_prediction 后在这里接入。
        raise NotImplementedError("anthropic 分支尚未实现；当前第一版仅实现 OpenAI。")

    raise ValueError(f"不支持的 model_type: {model_type}")
