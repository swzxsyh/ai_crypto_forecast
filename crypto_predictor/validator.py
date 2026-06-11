"""预测验证模块。"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from crypto_predictor.config import DB_PATH, DEFAULT_EXCHANGE_ID, DEFAULT_SIDEWAYS_THRESHOLD_PCT
from crypto_predictor.database import get_connection, init_db, iter_expired_pending_predictions
from crypto_predictor.exchange import build_exchange
from crypto_predictor.models import Direction
from crypto_predictor.time_utils import from_iso, to_iso, utc_now


def fetch_actual_price_at_or_after(
    symbol: str,
    expires_at: datetime,
    exchange_id: str = DEFAULT_EXCHANGE_ID,
) -> float:
    """获取预测到期后的真实价格。

    优先取 expires_at 之后第一根 1m K 线的 close；如果交易所暂未返回，
    则退回当前 ticker last。
    """

    exchange = build_exchange(exchange_id)
    since_ms = int(expires_at.timestamp() * 1000)

    candles = exchange.fetch_ohlcv(symbol, timeframe="1m", since=since_ms, limit=1)
    if candles:
        return float(candles[0][4])

    ticker = exchange.fetch_ticker(symbol)
    last_price = ticker.get("last")
    if last_price is None:
        raise RuntimeError(f"无法获取 {symbol} 的 ticker last price")
    return float(last_price)


def judge_direction_accuracy(
    prediction_direction: Direction,
    current_price: float,
    actual_price: float,
    sideways_threshold_pct: float = DEFAULT_SIDEWAYS_THRESHOLD_PCT,
) -> bool:
    """判断方向预测是否准确。"""

    if current_price <= 0:
        raise ValueError(f"current_price 必须大于 0: {current_price}")

    change_pct = (actual_price - current_price) / current_price

    if prediction_direction == "UP":
        return change_pct > sideways_threshold_pct
    if prediction_direction == "DOWN":
        return change_pct < -sideways_threshold_pct
    if prediction_direction == "SIDEWAYS":
        return abs(change_pct) <= sideways_threshold_pct

    raise ValueError(f"非法 prediction_direction: {prediction_direction}")


def check_and_update_accuracy(
    db_path: str = DB_PATH,
    sideways_threshold_pct: float = DEFAULT_SIDEWAYS_THRESHOLD_PCT,
) -> dict[str, Any]:
    """查询已到期预测，获取真实价格并更新准确性。"""

    init_db(db_path)
    checked_count = 0
    accurate_count = 0

    with get_connection(db_path) as conn:
        rows = list(iter_expired_pending_predictions(conn, to_iso(utc_now())))

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

            conn.execute(
                """
                UPDATE predictions
                SET actual_result_price = ?,
                    is_accurate = ?,
                    checked_at = ?
                WHERE id = ?
                """,
                (
                    actual_price,
                    1 if is_accurate else 0,
                    to_iso(utc_now()),
                    row["id"],
                ),
            )

            checked_count += 1
            accurate_count += 1 if is_accurate else 0

            # Binance 有公开接口频率限制；轻微暂停让批量验证更稳。
            time.sleep(0.2)

        conn.commit()

    direction_accuracy = (accurate_count / checked_count) if checked_count else None
    return {
        "checked_count": checked_count,
        "accurate_count": accurate_count,
        "direction_accuracy": direction_accuracy,
    }
