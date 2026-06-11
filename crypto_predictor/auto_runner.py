"""自动循环执行：定时预测、验证与纸面模拟。"""

from __future__ import annotations

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
from crypto_predictor.service import run_prediction_once, run_predictions_for_symbols
from crypto_predictor.validator import check_and_update_accuracy


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def should_execute_paper(prediction_result: dict[str, Any]) -> bool:
    """只有 LONG/SHORT 信号才执行纸面模拟。"""

    prediction = prediction_result.get("prediction", {})
    position_side = str(prediction.get("position_side", ""))
    return position_side in {"LONG", "SHORT"}


def should_execute_live(prediction_result: dict[str, Any], min_confidence: int = 40) -> bool:
    """真实下单额外要求：LONG/SHORT 且置信度 >= min_confidence。"""

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
    """执行一次自动任务周期。"""

    prediction_results = run_predictions_for_symbols(
        symbols=symbols,
        timeframe=timeframe,
        limit=limit,
        model_type=model_type,
    )

    paper_results: list[dict[str, Any]] = []
    if execute_paper:
        for item in prediction_results:
            if not should_execute_paper(item):
                continue
            prediction_id = int(item["prediction_id"])
            try:
                paper_result = execute_prediction_order(prediction_id=prediction_id, mode="paper", max_margin_per_trade=max_margin_per_trade)
                paper_results.append(
                    {
                        "prediction_id": prediction_id,
                        "status": "ok",
                        "trade_order_id": paper_result["trade_order_id"],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                paper_results.append(
                    {
                        "prediction_id": prediction_id,
                        "status": "error",
                        "error": str(exc),
                    }
                )

    live_results: list[dict[str, Any]] = []
    if execute_live:
        for item in prediction_results:
            if not should_execute_live(item):
                prediction = item.get("prediction", {})
                live_results.append({
                    "prediction_id": item.get("prediction_id"),
                    "status": "skipped",
                    "reason": f"置信度 {prediction.get('confidence', 0)} < 40，跳过真实下单",
                })
                continue
            prediction_id = int(item["prediction_id"])
            try:
                live_result = execute_prediction_order(prediction_id=prediction_id, mode="live", confirm="I_UNDERSTAND_LIVE_TRADING", max_margin_per_trade=max_margin_per_trade)
                live_results.append(
                    {
                        "prediction_id": prediction_id,
                        "status": "ok",
                        "trade_order_id": live_result["trade_order_id"],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                live_results.append(
                    {
                        "prediction_id": prediction_id,
                        "status": "error",
                        "error": str(exc),
                    }
                )

    check_result: dict[str, Any] | None = None
    if check_accuracy:
        check_result = check_and_update_accuracy()

    return {
        "started_at": _now_iso(),
        "predictions_created": len(prediction_results),
        "paper_orders": paper_results,
        "live_orders": live_results,
        "accuracy_check": check_result,
    }


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
    """按固定间隔执行自动任务；cycles=0 表示无限循环。"""

    init_db(db_path)
    chosen_symbols = tuple(symbols) if symbols else (DEFAULT_SYMBOL,)

    history: list[dict[str, Any]] = []
    cycle_no = 0
    interrupted = False

    try:
        while True:
            cycle_no += 1
            cycle_start = time.time()

            result = run_auto_cycle(
                symbols=chosen_symbols,
                timeframe=timeframe,
                limit=limit,
                model_type=model_type,
                execute_paper=execute_paper,
                execute_live=execute_live,
                check_accuracy=check_accuracy,
            )
            result["cycle"] = cycle_no
            history.append(result)

            if cycles > 0 and cycle_no >= cycles:
                break

            elapsed = time.time() - cycle_start
            sleep_seconds = max(0.0, interval_seconds - elapsed)
            if sleep_seconds > 0:
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
    """根据参数决定自动任务使用的交易对。"""

    if all_symbols:
        return DEFAULT_SYMBOLS
    if symbols:
        cleaned = tuple(item.strip() for item in symbols if item and item.strip())
        if cleaned:
            return cleaned
    return (DEFAULT_SYMBOL,) if not AUTO_RUN_PREDICT_ALL_SYMBOLS else DEFAULT_SYMBOLS
