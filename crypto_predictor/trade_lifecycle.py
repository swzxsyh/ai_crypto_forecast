"""Trade lifecycle manager for expiry-based position closing."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from crypto_predictor.broker.binance_broker import close_binance_position
from crypto_predictor.broker.models import CloseOrderRequest, CloseOrderResult
from crypto_predictor.broker.paper_broker import close_paper_order
from crypto_predictor.config import DB_PATH
from crypto_predictor.infrastructure.persistence.repository_factory import get_repository
from crypto_predictor.time_utils import from_iso, to_iso, utc_now
from crypto_predictor.validator import evaluate_prediction_window

logger = logging.getLogger(__name__)


def _repo(db_path: str = DB_PATH):
    repo = get_repository()
    if hasattr(repo, "db_path"):
        repo.db_path = db_path
    return repo


def get_next_trade_order_expiry(db_path: str = DB_PATH):
    """Return earliest open trade order expiry as datetime."""

    value = _repo(db_path).get_next_open_trade_order_expiry()
    return from_iso(value) if value else None


def close_expired_trade_orders(db_path: str = DB_PATH) -> dict[str, Any]:
    """Close open trade orders whose prediction window has expired."""

    repo = _repo(db_path)
    repo.init_schema()
    closed_count = 0
    error_count = 0
    results: list[dict[str, Any]] = []
    rows = list(repo.list_expired_open_trade_orders(to_iso(utc_now())))

    logger.info("Trade lifecycle scan: expired_open_orders=%s", len(rows))

    for row in rows:
        order_id = int(row["id"])
        try:
            result = close_trade_order_row(row, db_path=db_path)
            close_reason = str(result.raw_response.get("reason") or "expired")
            repo.update_trade_order_close(
                order_id,
                {
                    "closed_at": to_iso(utc_now()),
                    "close_status": "closed",
                    "close_reason": close_reason,
                    "exit_price": result.exit_price,
                    "close_order_id": result.close_order_id,
                    "close_message": result.message,
                    "close_raw_response": result.raw_response,
                },
            )
            closed_count += 1
            results.append(
                {
                    "trade_order_id": order_id,
                    "status": "closed",
                    "exit_price": result.exit_price,
                    "reason": close_reason,
                }
            )
            logger.info(
                "Trade order closed: id=%s symbol=%s mode=%s reason=%s exit_price=%s",
                order_id,
                row["symbol"],
                row["mode"],
                close_reason,
                result.exit_price,
            )
        except Exception as exc:  # noqa: BLE001
            error_count += 1
            repo.update_trade_order_close(
                order_id,
                {
                    "closed_at": to_iso(utc_now()),
                    "close_status": "close_error",
                    "close_reason": "error",
                    "close_message": str(exc),
                    "close_raw_response": {"error": str(exc)},
                },
            )
            results.append({"trade_order_id": order_id, "status": "error", "error": str(exc)})
            logger.exception("Trade order expiry close failed: id=%s", order_id)

    return {"checked_count": len(rows), "closed_count": closed_count, "error_count": error_count, "results": results}


def close_trade_order_row(row: Any, db_path: str = DB_PATH) -> CloseOrderResult:
    request = CloseOrderRequest(
        trade_order_id=int(row["id"]),
        prediction_id=int(row["prediction_id"]),
        symbol=str(row["symbol"]),
        position_side=str(row["position_side"]),
        entry_side=str(row["side"]),
        amount=float(row["amount"] or 0),
        mode=str(row["mode"]),  # type: ignore[arg-type]
        reason="expired",
    )

    if request.amount <= 0:
        raise RuntimeError(f"Cannot close order with non-positive amount: {request.amount}")

    if request.mode == "paper":
        prediction_row = _repo(db_path).get_prediction_by_id(request.prediction_id)
        if prediction_row is None:
            raise RuntimeError(f"Prediction not found for trade order: {request.prediction_id}")
        outcome = evaluate_prediction_window(prediction_row)
        close_reason = normalize_close_reason(outcome.reason)
        return close_paper_order(replace(request, reason=close_reason), exit_price=outcome.actual_price)

    if request.mode == "live":
        return close_binance_position(request)

    raise RuntimeError(f"Unsupported order mode for lifecycle close: {request.mode}")


def normalize_close_reason(reason: str) -> str:
    if reason == "take_profit":
        return "take_profit"
    if reason in {"stop_loss", "ambiguous_tp_sl_same_candle"}:
        return "stop_loss"
    return "expired"
