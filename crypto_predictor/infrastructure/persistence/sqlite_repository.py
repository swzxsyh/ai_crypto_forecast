"""SQLite repository adapter."""

from __future__ import annotations

from typing import Any

from crypto_predictor.broker.models import OrderResult
from crypto_predictor.config import DB_PATH
from crypto_predictor.models import MarketData, ModelType, Prediction

class SQLitePredictionRepository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def init_schema(self) -> None:
        from crypto_predictor import database
        database.init_db(self.db_path)

    def save_prediction(self, market_data: MarketData, prediction: Prediction, model_type: ModelType) -> int:
        from crypto_predictor import database
        return database.save_prediction(market_data, prediction, model_type, db_path=self.db_path)

    def count_predictions(self) -> int:
        from crypto_predictor import database
        return database.count_predictions(db_path=self.db_path)

    def list_recent_predictions(self, limit: int = 50, offset: int = 0) -> list[Any]:
        from crypto_predictor import database
        return database.list_recent_predictions(db_path=self.db_path, limit=limit, offset=offset)

    def get_prediction_by_id(self, prediction_id: int | None) -> Any | None:
        from crypto_predictor import database
        return database.get_prediction_by_id(prediction_id, db_path=self.db_path)

    def get_latest_prediction(self) -> Any | None:
        from crypto_predictor import database
        return database.get_latest_prediction(db_path=self.db_path)

    def get_latest_prediction_for_symbol(self, symbol: str) -> Any | None:
        from crypto_predictor import database
        return database.get_latest_prediction_for_symbol(symbol, db_path=self.db_path)

    def save_trade_order(self, prediction_id: int, result: OrderResult) -> int:
        from crypto_predictor import database
        return database.save_trade_order(prediction_id, result, db_path=self.db_path)

    def list_recent_trade_orders(self, limit: int = 50) -> list[Any]:
        from crypto_predictor import database
        return database.list_recent_trade_orders(db_path=self.db_path, limit=limit)

    def get_next_open_trade_order_expiry(self) -> str | None:
        from crypto_predictor import database
        return database.get_next_open_trade_order_expiry(db_path=self.db_path)

    def update_trade_order_close(self, order_id: int, payload: dict[str, object]) -> None:
        from crypto_predictor import database
        return database.update_trade_order_close(order_id, payload, db_path=self.db_path)

    def get_next_pending_prediction_expiry(self) -> str | None:
        from crypto_predictor.database import get_connection, init_db

        init_db(self.db_path)
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT MIN(expires_at) AS next_expires_at
                FROM predictions
                WHERE actual_result_price IS NULL
                """
            ).fetchone()
        return row["next_expires_at"] if row and row["next_expires_at"] else None

    def list_expired_pending_predictions(self, now_iso: str) -> list[Any]:
        from crypto_predictor.database import get_connection, init_db, iter_expired_pending_predictions

        init_db(self.db_path)
        with get_connection(self.db_path) as conn:
            return list(iter_expired_pending_predictions(conn, now_iso))

    def update_prediction_accuracy(
        self,
        prediction_id: int,
        actual_price: float,
        is_accurate: bool,
        checked_at: str,
        validation_reason: str | None = None,
        validation_event_time: str | None = None,
    ) -> None:
        from crypto_predictor.database import get_connection, init_db

        init_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE predictions
                SET actual_result_price = ?,
                    is_accurate = ?,
                    checked_at = ?,
                    validation_reason = ?,
                    validation_event_time = ?
                WHERE id = ?
                """,
                (actual_price, 1 if is_accurate else 0, checked_at, validation_reason, validation_event_time, prediction_id),
            )
            conn.commit()

    def list_expired_open_trade_orders(self, now_iso: str) -> list[Any]:
        from crypto_predictor.database import get_connection, init_db, iter_expired_open_trade_orders

        init_db(self.db_path)
        with get_connection(self.db_path) as conn:
            return list(iter_expired_open_trade_orders(conn, now_iso))
    def list_chart_predictions(
        self,
        symbol: str | None = None,
        limit: int = 100,
        start_utc: str | None = None,
        end_utc: str | None = None,
    ) -> list[Any]:
        from crypto_predictor import database
        return database.list_chart_predictions(
            db_path=self.db_path,
            symbol=symbol,
            limit=limit,
            start_utc=start_utc,
            end_utc=end_utc,
        )

    def get_overall_accuracy(self) -> dict[str, object]:
        from crypto_predictor import database
        return database.get_overall_accuracy(db_path=self.db_path)

    def save_auto_run_log(self, payload: dict[str, object]) -> int:
        from crypto_predictor import database
        return database.save_auto_run_log(payload, db_path=self.db_path)

    def count_auto_run_logs(self) -> int:
        from crypto_predictor import database
        return database.count_auto_run_logs(db_path=self.db_path)

    def list_recent_auto_run_logs(self, limit: int = 50, offset: int = 0) -> list[Any]:
        from crypto_predictor import database
        return database.list_recent_auto_run_logs(db_path=self.db_path, limit=limit, offset=offset)

    def get_auto_run_log_stats(self) -> dict[str, object]:
        from crypto_predictor import database
        return database.get_auto_run_log_stats(db_path=self.db_path)

    def save_user_advice_action(self, payload: dict[str, object]) -> int:
        from crypto_predictor import database
        return database.save_user_advice_action(payload, db_path=self.db_path)

    def list_recent_user_advice_actions(self, limit: int = 50) -> list[Any]:
        from crypto_predictor import database
        return database.list_recent_user_advice_actions(db_path=self.db_path, limit=limit)

