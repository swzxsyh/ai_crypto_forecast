"""Prediction expiry validation."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from crypto_predictor.config import DB_PATH, DEFAULT_EXCHANGE_ID, DEFAULT_SIDEWAYS_THRESHOLD_PCT
from crypto_predictor.exchange import build_exchange
from crypto_predictor.models import Direction
from crypto_predictor.repositories import get_repository
from crypto_predictor.time_utils import from_iso, to_iso, utc_now

logger = logging.getLogger(__name__)


def fetch_actual_price_at_or_after(
    symbol: str,
    expires_at: datetime,
    exchange_id: str = DEFAULT_EXCHANGE_ID,
) -> float:
    """Fetch the first 1m close at or after the prediction expiry timestamp."""

    exchange = build_exchange(exchange_id)
    since_ms = int(expires_at.timestamp() * 1000)
    logger.info("Validation price fetch: symbol=%s expires_at=%s since_ms=%s", symbol, to_iso(expires_at), since_ms)

    candles = exchange.fetch_ohlcv(symbol, timeframe="1m", since=since_ms, limit=1)
    if candles:
        candle = candles[0]
        logger.info(
            "Validation price resolved from 1m candle: symbol=%s candle_ts_ms=%s close=%s",
            symbol,
            int(candle[0]),
            float(candle[4]),
        )
        return float(candle[4])

    ticker = exchange.fetch_ticker(symbol)
    last_price = ticker.get("last")
    if last_price is None:
        raise RuntimeError(f"Unable to fetch ticker last price for {symbol}")
    logger.warning("Validation fell back to ticker last price: symbol=%s price=%s", symbol, last_price)
    return float(last_price)


def judge_direction_accuracy(
    prediction_direction: Direction,
    current_price: float,
    actual_price: float,
    sideways_threshold_pct: float = DEFAULT_SIDEWAYS_THRESHOLD_PCT,
) -> bool:
    """Judge whether predicted direction matches the expiry price move."""

    if current_price <= 0:
        raise ValueError(f"current_price must be greater than 0: {current_price}")

    change_pct = (actual_price - current_price) / current_price

    if prediction_direction == "UP":
        return change_pct > sideways_threshold_pct
    if prediction_direction == "DOWN":
        return change_pct < -sideways_threshold_pct
    if prediction_direction == "SIDEWAYS":
        return abs(change_pct) <= sideways_threshold_pct

    raise ValueError(f"Invalid prediction_direction: {prediction_direction}")


def _repo(db_path: str = DB_PATH):
    repo = get_repository()
    if hasattr(repo, "db_path"):
        repo.db_path = db_path
    return repo


def get_next_pending_prediction_expiry(db_path: str = DB_PATH) -> datetime | None:
    """Return the earliest expires_at among pending predictions."""

    value = _repo(db_path).get_next_pending_prediction_expiry()
    return from_iso(value) if value else None


def check_and_update_accuracy(
    db_path: str = DB_PATH,
    sideways_threshold_pct: float = DEFAULT_SIDEWAYS_THRESHOLD_PCT,
) -> dict[str, Any]:
    """Check expired pending predictions and update accuracy using expiry-time price."""

    repo = _repo(db_path)
    repo.init_schema()
    checked_count = 0
    accurate_count = 0
    rows = list(repo.list_expired_pending_predictions(to_iso(utc_now())))
    logger.info("Accuracy validation scan: expired_pending=%s", len(rows))

    for row in rows:
        expires_at = from_iso(row["expires_at"])
        actual_price = fetch_actual_price_at_or_after(
            symbol=row["symbol"],
            expires_at=expires_at,
            exchange_id=row["exchange"],
        )
        is_accurate = judge_direction_accuracy(
            prediction_direction=row["prediction_direction"],
            current_price=float(row["current_price"]),
            actual_price=actual_price,
            sideways_threshold_pct=sideways_threshold_pct,
        )

        repo.update_prediction_accuracy(
            prediction_id=int(row["id"]),
            actual_price=actual_price,
            is_accurate=bool(is_accurate),
            checked_at=to_iso(utc_now()),
        )

        checked_count += 1
        accurate_count += 1 if is_accurate else 0
        logger.info(
            "Prediction validated: id=%s symbol=%s direction=%s expires_at=%s actual_price=%s accurate=%s",
            row["id"],
            row["symbol"],
            row["prediction_direction"],
            row["expires_at"],
            actual_price,
            bool(is_accurate),
        )
        time.sleep(0.2)

    direction_accuracy = (accurate_count / checked_count) if checked_count else None
    return {
        "checked_count": checked_count,
        "accurate_count": accurate_count,
        "direction_accuracy": direction_accuracy,
    }
