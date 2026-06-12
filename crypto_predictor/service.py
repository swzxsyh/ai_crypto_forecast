"""Prediction orchestration service."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Iterable

from crypto_predictor.ai.predictor import get_ai_prediction
from crypto_predictor.config import DB_PATH, DEFAULT_LIMIT, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME
from crypto_predictor.contract import enrich_contract_metrics
from crypto_predictor.infrastructure.persistence.repository_factory import get_repository
from crypto_predictor.market_data import fetch_latest_ohlcv
from crypto_predictor.models import ModelType

logger = logging.getLogger(__name__)


def run_prediction_once(
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    limit: int = DEFAULT_LIMIT,
    model_type: ModelType = "openai",
    db_path: str = DB_PATH,
) -> dict[str, Any]:
    """Fetch market data, call AI, enrich contract metrics, and save prediction."""

    logger.info("Prediction started: symbol=%s timeframe=%s limit=%s model=%s", symbol, timeframe, limit, model_type)
    try:
        market_data = fetch_latest_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)
    except Exception:
        logger.exception("Prediction failed before AI stage: symbol=%s stage=market_data", symbol)
        raise

    try:
        logger.info("AI prediction stage started: symbol=%s model=%s", symbol, model_type)
        raw_prediction = get_ai_prediction(market_data, model_type=model_type)
        prediction = enrich_contract_metrics(raw_prediction, entry_price=market_data.current_price)
        logger.info(
            "AI prediction stage succeeded: symbol=%s direction=%s side=%s confidence=%s",
            symbol,
            prediction.direction,
            prediction.position_side,
            prediction.confidence,
        )
    except Exception:
        logger.exception("Prediction failed in AI/contract stage: symbol=%s", symbol)
        raise

    try:
        repo = get_repository()
        if hasattr(repo, "db_path"):
            repo.db_path = db_path
        prediction_id = repo.save_prediction(market_data, prediction, model_type=model_type)
        logger.info("Prediction saved: id=%s symbol=%s current_price=%s", prediction_id, symbol, market_data.current_price)
    except Exception:
        logger.exception("Prediction failed in database stage: symbol=%s", symbol)
        raise

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
    """Create predictions sequentially for multiple symbols."""

    symbol_list = tuple(symbols)
    logger.info("Batch prediction started: symbols=%s timeframe=%s limit=%s", list(symbol_list), timeframe, limit)
    results: list[dict[str, Any]] = []
    for symbol in symbol_list:
        results.append(
            run_prediction_once(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                model_type=model_type,
                db_path=db_path,
            )
        )
    logger.info("Batch prediction finished: created=%s symbols=%s", len(results), list(symbol_list))
    return results
