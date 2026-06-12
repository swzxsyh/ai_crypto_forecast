"""Scheduled auto runner: prediction, execution, and validation cycles."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Iterable

from crypto_predictor.broker.executor import execute_prediction_order
from crypto_predictor.config import (
    AUTO_RUN_CHECK_ACCURACY,
    AUTO_RUN_EXECUTE_LIVE,
    AUTO_RUN_EXECUTE_PAPER,
    AUTO_RUN_INTERVAL_SECONDS,
    AUTO_RUN_MODEL_TYPE,
    AUTO_RUN_PREDICT_ALL_SYMBOLS,
    DB_PATH,
    DEFAULT_LIMIT,
    DEFAULT_SYMBOL,
    DEFAULT_SYMBOLS,
    DEFAULT_TIMEFRAME,
)
from crypto_predictor.database import init_db
from crypto_predictor.service import run_predictions_for_symbols
from crypto_predictor.validator import check_and_update_accuracy

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def should_execute_paper(prediction_result: dict[str, Any]) -> bool:
    """Only LONG/SHORT signals should create paper orders."""

    prediction = prediction_result.get("prediction", {})
    position_side = str(prediction.get("position_side", ""))
    return position_side in {"LONG", "SHORT"}


def should_execute_live(prediction_result: dict[str, Any], min_confidence: int = 40) -> bool:
    """Live execution requires LONG/SHORT and minimum confidence."""

    prediction = prediction_result.get("prediction", {})
    position_side = str(prediction.get("position_side", ""))
    confidence = int(prediction.get("confidence", 0))
    return position_side in {"LONG", "SHORT"} and confidence >= min_confidence


def run_auto_cycle(
    symbols: Iterable[str],
    timeframe: str = DEFAULT_TIMEFRAME,
    limit: int = DEFAULT_LIMIT,
    model_type: str = AUTO_RUN_MODEL_TYPE,
    execute_paper: bool = AUTO_RUN_EXECUTE_PAPER,
    execute_live: bool = AUTO_RUN_EXECUTE_LIVE,
    check_accuracy: bool = AUTO_RUN_CHECK_ACCURACY,
    max_margin_per_trade: float | None = None,
) -> dict[str, Any]:
    """Run one auto task cycle."""

    symbol_list = tuple(symbols)
    logger.info("================== Start scheduled prediction cycle ==================")
    logger.info(
        "Cycle params: symbols=%s timeframe=%s limit=%s model=%s paper=%s live=%s check_accuracy=%s",
        list(symbol_list),
        timeframe,
        limit,
        model_type,
        execute_paper,
        execute_live,
        check_accuracy,
    )

    try:
        prediction_results = run_predictions_for_symbols(
            symbols=symbol_list,
            timeframe=timeframe,
            limit=limit,
            model_type=model_type,
        )
        logger.info("Prediction stage completed: created=%s", len(prediction_results))
    except Exception as exc:
        logger.error("This prediction cycle failed in market/AI stage: %s", exc)
        logger.error("Hint: if the error mentions Binance, check rate limit, IP blocking, proxy settings, or network congestion.")
        logger.info("================== Scheduled prediction cycle skipped ==================")
        raise

    paper_results: list[dict[str, Any]] = []
    if execute_paper:
        logger.info("Paper execution stage started")
        for item in prediction_results:
            if not should_execute_paper(item):
                continue
            prediction_id = int(item["prediction_id"])
            try:
                paper_result = execute_prediction_order(
                    prediction_id=prediction_id,
                    mode="paper",
                    max_margin_per_trade=max_margin_per_trade,
                )
                paper_results.append(
                    {
                        "prediction_id": prediction_id,
                        "status": "ok",
                        "trade_order_id": paper_result["trade_order_id"],
                    }
                )
                logger.info("Paper execution succeeded: prediction_id=%s trade_order_id=%s", prediction_id, paper_result["trade_order_id"])
            except Exception as exc:  # noqa: BLE001
                paper_results.append({"prediction_id": prediction_id, "status": "error", "error": str(exc)})
                logger.error("Paper execution failed: prediction_id=%s error=%s", prediction_id, exc)

    live_results: list[dict[str, Any]] = []
    if execute_live:
        logger.info("Live execution stage started")
        for item in prediction_results:
            if not should_execute_live(item):
                prediction = item.get("prediction", {})
                live_results.append(
                    {
                        "prediction_id": item.get("prediction_id"),
                        "status": "skipped",
                        "reason": f"confidence {prediction.get('confidence', 0)} < 40 or no LONG/SHORT signal",
                    }
                )
                continue
            prediction_id = int(item["prediction_id"])
            try:
                live_result = execute_prediction_order(
                    prediction_id=prediction_id,
                    mode="live",
                    confirm="I_UNDERSTAND_LIVE_TRADING",
                    max_margin_per_trade=max_margin_per_trade,
                )
                live_results.append(
                    {
                        "prediction_id": prediction_id,
                        "status": "ok",
                        "trade_order_id": live_result["trade_order_id"],
                    }
                )
                logger.info("Live execution succeeded: prediction_id=%s trade_order_id=%s", prediction_id, live_result["trade_order_id"])
            except Exception as exc:  # noqa: BLE001
                live_results.append({"prediction_id": prediction_id, "status": "error", "error": str(exc)})
                logger.error("Live execution failed: prediction_id=%s error=%s", prediction_id, exc)

    check_result: dict[str, Any] | None = None
    if check_accuracy:
        try:
            logger.info("Accuracy check stage started")
            check_result = check_and_update_accuracy()
            logger.info("Accuracy check completed: %s", check_result)
        except Exception as exc:
            logger.error("Accuracy check failed: %s", exc)
            raise

    result = {
        "started_at": _now_iso(),
        "predictions_created": len(prediction_results),
        "paper_orders": paper_results,
        "live_orders": live_results,
        "accuracy_check": check_result,
    }
    logger.info("================== Scheduled prediction cycle finished ==================")
    return result


def run_auto_loop(
    interval_seconds: int = AUTO_RUN_INTERVAL_SECONDS,
    cycles: int = 0,
    symbols: Iterable[str] | None = None,
    timeframe: str = DEFAULT_TIMEFRAME,
    limit: int = DEFAULT_LIMIT,
    model_type: str = AUTO_RUN_MODEL_TYPE,
    execute_paper: bool = AUTO_RUN_EXECUTE_PAPER,
    execute_live: bool = AUTO_RUN_EXECUTE_LIVE,
    check_accuracy: bool = AUTO_RUN_CHECK_ACCURACY,
    db_path: str = DB_PATH,
) -> dict[str, Any]:
    """Run auto cycles at a fixed interval; cycles=0 means forever."""

    init_db(db_path)
    chosen_symbols = tuple(symbols) if symbols else (DEFAULT_SYMBOL,)

    history: list[dict[str, Any]] = []
    cycle_no = 0
    interrupted = False

    try:
        while True:
            cycle_no += 1
            cycle_start = time.time()

            try:
                result = run_auto_cycle(
                    symbols=chosen_symbols,
                    timeframe=timeframe,
                    limit=limit,
                    model_type=model_type,
                    execute_paper=execute_paper,
                    execute_live=execute_live,
                    check_accuracy=check_accuracy,
                )
            except Exception as exc:  # noqa: BLE001
                result = {
                    "started_at": _now_iso(),
                    "status": "error",
                    "error": str(exc),
                    "predictions_created": 0,
                    "paper_orders": [],
                    "live_orders": [],
                    "accuracy_check": None,
                }
                logger.error("Auto loop cycle failed and will continue next interval: cycle=%s error=%s", cycle_no, exc)

            result["cycle"] = cycle_no
            history.append(result)

            if cycles > 0 and cycle_no >= cycles:
                break

            elapsed = time.time() - cycle_start
            sleep_seconds = max(0.0, interval_seconds - elapsed)
            if sleep_seconds > 0:
                logger.info("Waiting %.2f seconds before next auto cycle", sleep_seconds)
                time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        interrupted = True

    return {
        "cycles_completed": cycle_no,
        "interrupted": interrupted,
        "symbols": list(chosen_symbols),
        "interval_seconds": interval_seconds,
        "timeframe": timeframe,
        "limit": limit,
        "model_type": model_type,
        "execute_paper": execute_paper,
        "execute_live": execute_live,
        "check_accuracy": check_accuracy,
        "history": history,
    }


def resolve_auto_symbols(all_symbols: bool, symbols: Iterable[str] | None) -> tuple[str, ...]:
    """Resolve auto task symbols from CLI/config flags."""

    if all_symbols:
        return DEFAULT_SYMBOLS
    if symbols:
        cleaned = tuple(item.strip() for item in symbols if item and item.strip())
        if cleaned:
            return cleaned
    return (DEFAULT_SYMBOL,) if not AUTO_RUN_PREDICT_ALL_SYMBOLS else DEFAULT_SYMBOLS
