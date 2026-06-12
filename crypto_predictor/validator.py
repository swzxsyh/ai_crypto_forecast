"""Prediction expiry validation."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crypto_predictor.config import DB_PATH, DEFAULT_EXCHANGE_ID, DEFAULT_SIDEWAYS_THRESHOLD_PCT
from crypto_predictor.exchange import build_exchange
from crypto_predictor.infrastructure.persistence.repository_factory import get_repository
from crypto_predictor.models import Direction
from crypto_predictor.time_utils import from_iso, to_iso, utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationOutcome:
    """Result of replaying the prediction window."""

    actual_price: float
    is_accurate: bool
    reason: str
    event_time: str | None = None


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


def fetch_ohlcv_window(
    symbol: str,
    start_at: datetime,
    end_at: datetime,
    exchange_id: str = DEFAULT_EXCHANGE_ID,
) -> list[list[Any]]:
    """Fetch 1m candles covering [start_at, end_at] for path replay."""

    if end_at < start_at:
        return []

    exchange = build_exchange(exchange_id)
    start_ms = int(start_at.timestamp() * 1000)
    end_ms = int(end_at.timestamp() * 1000)
    since_ms = start_ms
    candles: list[list[Any]] = []

    while since_ms <= end_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe="1m", since=since_ms, limit=1000)
        if not batch:
            break

        progressed = False
        for item in batch:
            candle_ts = int(item[0])
            if candle_ts < start_ms:
                continue
            if candle_ts > end_ms:
                return candles
            candles.append(item)
            since_ms = candle_ts + 60_000
            progressed = True

        if not progressed:
            break
        if len(batch) < 1000:
            break

    return candles


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


def evaluate_prediction_window(
    row: Any,
    sideways_threshold_pct: float = DEFAULT_SIDEWAYS_THRESHOLD_PCT,
) -> ValidationOutcome:
    """Replay the prediction interval and prefer TP/SL path outcome when available."""

    symbol = str(row["symbol"])
    exchange_id = str(row["exchange"] or DEFAULT_EXCHANGE_ID)
    prediction_direction = row["prediction_direction"]
    position_side = str(row["position_side"] or "NO_TRADE")
    entry_price = float(row["entry_price"] or row["current_price"])
    take_profit_price = float(row["take_profit_price"] or 0)
    stop_loss_price = float(row["stop_loss_price"] or 0)
    start_at = from_iso(row["prediction_time"])
    expires_at = from_iso(row["expires_at"])

    if position_side in {"LONG", "SHORT"} and take_profit_price > 0 and stop_loss_price > 0:
        candles = fetch_ohlcv_window(symbol=symbol, start_at=start_at, end_at=expires_at, exchange_id=exchange_id)
        outcome = evaluate_tp_sl_path(
            candles=candles,
            position_side=position_side,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
        )
        if outcome is not None:
            return outcome

    actual_price = fetch_actual_price_at_or_after(symbol=symbol, expires_at=expires_at, exchange_id=exchange_id)
    is_accurate = judge_direction_accuracy(
        prediction_direction=prediction_direction,
        current_price=entry_price,
        actual_price=actual_price,
        sideways_threshold_pct=sideways_threshold_pct,
    )
    return ValidationOutcome(actual_price=actual_price, is_accurate=is_accurate, reason="expiry_close", event_time=to_iso(expires_at))


def evaluate_tp_sl_path(
    candles: list[list[Any]],
    position_side: str,
    take_profit_price: float,
    stop_loss_price: float,
) -> ValidationOutcome | None:
    """Return first TP/SL event from 1m candles, using conservative handling for ambiguous candles."""

    for candle in candles:
        candle_time = datetime.fromtimestamp(int(candle[0]) / 1000, tz=utc_now().tzinfo)
        high = float(candle[2])
        low = float(candle[3])

        if position_side == "LONG":
            hit_tp = high >= take_profit_price
            hit_sl = low <= stop_loss_price
            if hit_tp and hit_sl:
                return ValidationOutcome(stop_loss_price, False, "ambiguous_tp_sl_same_candle", to_iso(candle_time))
            if hit_tp:
                return ValidationOutcome(take_profit_price, True, "take_profit", to_iso(candle_time))
            if hit_sl:
                return ValidationOutcome(stop_loss_price, False, "stop_loss", to_iso(candle_time))

        if position_side == "SHORT":
            hit_tp = low <= take_profit_price
            hit_sl = high >= stop_loss_price
            if hit_tp and hit_sl:
                return ValidationOutcome(stop_loss_price, False, "ambiguous_tp_sl_same_candle", to_iso(candle_time))
            if hit_tp:
                return ValidationOutcome(take_profit_price, True, "take_profit", to_iso(candle_time))
            if hit_sl:
                return ValidationOutcome(stop_loss_price, False, "stop_loss", to_iso(candle_time))

    return None


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
    """Check expired pending predictions and update accuracy using interval path replay."""

    repo = _repo(db_path)
    repo.init_schema()
    checked_count = 0
    accurate_count = 0
    rows = list(repo.list_expired_pending_predictions(to_iso(utc_now())))
    logger.info("Accuracy validation scan: expired_pending=%s", len(rows))

    for row in rows:
        outcome = evaluate_prediction_window(row, sideways_threshold_pct=sideways_threshold_pct)

        repo.update_prediction_accuracy(
            prediction_id=int(row["id"]),
            actual_price=outcome.actual_price,
            is_accurate=bool(outcome.is_accurate),
            checked_at=to_iso(utc_now()),
            validation_reason=outcome.reason,
            validation_event_time=outcome.event_time,
        )

        checked_count += 1
        accurate_count += 1 if outcome.is_accurate else 0
        logger.info(
            "Prediction validated: id=%s symbol=%s direction=%s expires_at=%s actual_price=%s accurate=%s reason=%s event_time=%s",
            row["id"],
            row["symbol"],
            row["prediction_direction"],
            row["expires_at"],
            outcome.actual_price,
            bool(outcome.is_accurate),
            outcome.reason,
            outcome.event_time,
        )
        time.sleep(0.2)

    direction_accuracy = (accurate_count / checked_count) if checked_count else None
    return {
        "checked_count": checked_count,
        "accurate_count": accurate_count,
        "direction_accuracy": direction_accuracy,
    }

