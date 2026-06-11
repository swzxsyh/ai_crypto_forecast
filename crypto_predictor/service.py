"""业务编排层。"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from crypto_predictor.ai.predictor import get_ai_prediction
from crypto_predictor.config import DB_PATH, DEFAULT_LIMIT, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME
from crypto_predictor.contract import enrich_contract_metrics
from crypto_predictor.database import save_prediction
from crypto_predictor.market_data import fetch_latest_ohlcv
from crypto_predictor.models import ModelType


def run_prediction_once(
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    limit: int = DEFAULT_LIMIT,
    model_type: ModelType = "openai",
    db_path: str = DB_PATH,
) -> dict[str, Any]:
    """获取行情 -> AI 预测 -> 写入数据库。"""

    market_data = fetch_latest_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)
    raw_prediction = get_ai_prediction(market_data, model_type=model_type)
    prediction = enrich_contract_metrics(raw_prediction, entry_price=market_data.current_price)
    prediction_id = save_prediction(market_data, prediction, model_type=model_type, db_path=db_path)

    return {
        "prediction_id": prediction_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "current_price": market_data.current_price,
        "model_type": model_type,
        "prediction": asdict(prediction),
    }


def run_predictions_for_symbols(
    symbols: Iterable[str],
    timeframe: str = DEFAULT_TIMEFRAME,
    limit: int = DEFAULT_LIMIT,
    model_type: ModelType = "openai",
    db_path: str = DB_PATH,
) -> list[dict[str, Any]]:
    """按顺序为多个交易对创建预测。"""

    results: list[dict[str, Any]] = []
    for symbol in symbols:
        results.append(
            run_prediction_once(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                model_type=model_type,
                db_path=db_path,
            )
        )
    return results
