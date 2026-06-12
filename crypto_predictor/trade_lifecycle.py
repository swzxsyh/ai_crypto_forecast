"""Trade lifecycle manager for expiry-based position closing."""

from __future__ import annotations

import logging
from typing import Any

from crypto_predictor.broker.binance_broker import close_binance_position
from crypto_predictor.broker.models import CloseOrderRequest, CloseOrderResult
from crypto_predictor.broker.paper_broker import close_paper_order
from crypto_predictor.config import DB_PATH
from crypto_predictor.database import (
    get_connection,
    get_next_open_trade_order_expiry,
    init_db,
    iter_expired_open_trade_orders,
    update_trade_order_close,
)
from crypto_predictor.time_utils import from_iso, to_iso, utc_now
from crypto_predictor.validator import fetch_actual_price_at_or_after

logger = logging.getLogger(__name__)


def get_next_trade_order_expiry(db_path: str = DB_PATH):
    """Return earliest open trade order expiry as datetime."""

    value = get_next_open_trade_order_expiry(db_path=db_path)
    return from_iso(value) if value else None


def close_expired_trade_orders(db_path: str = DB_PATH) -> dict[str, Any]:
    """Close open trade orders whose prediction window has expired."""

    init_db(db_path)
    closed_count = 0
    error_count = 0
    results: list[dict[str, Any]] = []

    with get_connection(db_path) as conn:
        rows = list(iter_expired_open_trade_orders(conn, to_iso(utc_now())))

    logger.info("Trade lifecycle scan: expired_open_orders=%s", len(rows))

    for row in rows:
        order_id = int(row["id"])
        try:
            result = close_trade_order_row(row)
            update_trade_order_close(
                order_id,
                {
                    "closed_at": to_iso(utc_now()),
                    "close_status": "closed",
                    "close_reason": "expired",
                    "exit_price": result.exit_price,
                    "close_order_id": result.close_order_id,
                    "close_message": result.message,
                    "close_raw_response": result.raw_response,
                },
                db_path=db_path,
            )
            closed_count += 1
            results.append({"trade_order_id": order_id, "status": "closed", "exit_price": result.exit_price})
            logger.info("Trade order closed at expiry: id=%s symbol=%s mode=%s", order_id, row["symbol"], row["mode"])
        except Exception as exc:  # noqa: BLE001
            error_count += 1
            update_trade_order_close(
                order_id,
                {
                    "closed_at": to_iso(utc_now()),
                    "close_status": "close_error",
                    "close_reason": "expired",
                    "close_message": str(exc),
                    "close_raw_response": {"error": str(exc)},
                },
                db_path=db_path,
            )
            results.append({"trade_order_id": order_id, "status": "error", "error": str(exc)})
            logger.exception("Trade order expiry close failed: id=%s", order_id)

    return {"checked_count": len(rows), "closed_count": closed_count, "error_count": error_count, "results": results}


def close_trade_order_row(row: Any) -> CloseOrderResult:
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
        expires_at = from_iso(str(row["expires_at"] or row["prediction_expires_at"]))
        exit_price = fetch_actual_price_at_or_after(symbol=request.symbol, expires_at=expires_at)
        return close_paper_order(request, exit_price=exit_price)

    if request.mode == "live":
        return close_binance_position(request)

    raise RuntimeError(f"Unsupported order mode for lifecycle close: {request.mode}")
