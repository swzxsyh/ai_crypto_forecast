"""Persistence repository boundary."""

from __future__ import annotations

from typing import Any, Protocol

from crypto_predictor.broker.models import OrderResult
from crypto_predictor.config import DB_BACKEND, DB_PATH, POSTGRES_DSN
from crypto_predictor.models import MarketData, ModelType, Prediction


class PredictionRepository(Protocol):
    def init_schema(self) -> None: ...
    def save_prediction(self, market_data: MarketData, prediction: Prediction, model_type: ModelType) -> int: ...
    def count_predictions(self) -> int: ...
    def list_recent_predictions(self, limit: int = 50, offset: int = 0) -> list[Any]: ...
    def get_prediction_by_id(self, prediction_id: int | None) -> Any | None: ...
    def get_latest_prediction(self) -> Any | None: ...
    def get_latest_prediction_for_symbol(self, symbol: str) -> Any | None: ...
    def save_trade_order(self, prediction_id: int, result: OrderResult) -> int: ...
    def list_recent_trade_orders(self, limit: int = 50) -> list[Any]: ...
    def get_next_open_trade_order_expiry(self) -> str | None: ...
    def update_trade_order_close(self, order_id: int, payload: dict[str, object]) -> None: ...
    def list_chart_predictions(
        self,
        symbol: str | None = None,
        limit: int = 100,
        start_utc: str | None = None,
        end_utc: str | None = None,
    ) -> list[Any]: ...
    def get_overall_accuracy(self) -> dict[str, object]: ...
    def save_auto_run_log(self, payload: dict[str, object]) -> int: ...
    def count_auto_run_logs(self) -> int: ...
    def list_recent_auto_run_logs(self, limit: int = 50, offset: int = 0) -> list[Any]: ...
    def get_auto_run_log_stats(self) -> dict[str, object]: ...
    def save_user_advice_action(self, payload: dict[str, object]) -> int: ...
    def list_recent_user_advice_actions(self, limit: int = 50) -> list[Any]: ...


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


class PostgreSQLPredictionRepository:
    def __init__(self, dsn: str = POSTGRES_DSN):
        self.dsn = dsn

    def init_schema(self) -> None:
        if not self.dsn:
            raise RuntimeError("POSTGRES_DSN is empty; set database.postgres_dsn in config.yaml")
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL backend requires psycopg. Install with: pip install 'psycopg[binary]>=3.1'") from exc
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                for statement in POSTGRES_SCHEMA:
                    cur.execute(statement)
            conn.commit()

    def _not_implemented(self) -> None:
        raise NotImplementedError(
            "PostgreSQL repository schema creation is available, but query/write methods "
            "still need to be implemented before DB_BACKEND=postgresql can run the app."
        )

    def save_prediction(self, market_data: MarketData, prediction: Prediction, model_type: ModelType) -> int: self._not_implemented()
    def count_predictions(self) -> int: self._not_implemented()
    def list_recent_predictions(self, limit: int = 50, offset: int = 0) -> list[Any]: self._not_implemented()
    def get_prediction_by_id(self, prediction_id: int | None) -> Any | None: self._not_implemented()
    def get_latest_prediction(self) -> Any | None: self._not_implemented()
    def get_latest_prediction_for_symbol(self, symbol: str) -> Any | None: self._not_implemented()
    def save_trade_order(self, prediction_id: int, result: OrderResult) -> int: self._not_implemented()
    def list_recent_trade_orders(self, limit: int = 50) -> list[Any]: self._not_implemented()
    def get_next_open_trade_order_expiry(self) -> str | None: self._not_implemented()
    def update_trade_order_close(self, order_id: int, payload: dict[str, object]) -> None: self._not_implemented()
    def list_chart_predictions(self, symbol: str | None = None, limit: int = 100, start_utc: str | None = None, end_utc: str | None = None) -> list[Any]: self._not_implemented()
    def get_overall_accuracy(self) -> dict[str, object]: self._not_implemented()
    def save_auto_run_log(self, payload: dict[str, object]) -> int: self._not_implemented()
    def count_auto_run_logs(self) -> int: self._not_implemented()
    def list_recent_auto_run_logs(self, limit: int = 50, offset: int = 0) -> list[Any]: self._not_implemented()
    def get_auto_run_log_stats(self) -> dict[str, object]: self._not_implemented()
    def save_user_advice_action(self, payload: dict[str, object]) -> int: self._not_implemented()
    def list_recent_user_advice_actions(self, limit: int = 50) -> list[Any]: self._not_implemented()


def get_repository() -> PredictionRepository:
    if DB_BACKEND == "postgresql":
        return PostgreSQLPredictionRepository()
    return SQLitePredictionRepository()


POSTGRES_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS predictions (
        id BIGSERIAL PRIMARY KEY,
        prediction_time TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        exchange TEXT NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        current_price DOUBLE PRECISION NOT NULL,
        prediction_model TEXT NOT NULL,
        prediction_direction TEXT NOT NULL,
        target_price DOUBLE PRECISION NOT NULL,
        confidence INTEGER NOT NULL,
        position_side TEXT NOT NULL DEFAULT 'NO_TRADE',
        margin_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
        leverage INTEGER NOT NULL DEFAULT 0,
        entry_price DOUBLE PRECISION NOT NULL DEFAULT 0,
        take_profit_price DOUBLE PRECISION NOT NULL DEFAULT 0,
        stop_loss_price DOUBLE PRECISION NOT NULL DEFAULT 0,
        notional_value DOUBLE PRECISION NOT NULL DEFAULT 0,
        expected_profit DOUBLE PRECISION NOT NULL DEFAULT 0,
        expected_loss DOUBLE PRECISION NOT NULL DEFAULT 0,
        risk_reward_ratio DOUBLE PRECISION,
        actual_result_price DOUBLE PRECISION,
        is_accurate INTEGER,
        checked_at TEXT,
        raw_market_data TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_orders (
        id BIGSERIAL PRIMARY KEY,
        prediction_id BIGINT NOT NULL REFERENCES predictions(id),
        created_at TEXT NOT NULL,
        mode TEXT NOT NULL,
        exchange TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        amount DOUBLE PRECISION NOT NULL,
        leverage INTEGER NOT NULL,
        status TEXT NOT NULL,
        entry_order_id TEXT,
        take_profit_order_id TEXT,
        stop_loss_order_id TEXT,
        message TEXT NOT NULL,
        raw_response TEXT NOT NULL,
        expires_at TEXT,
        closed_at TEXT,
        close_status TEXT NOT NULL DEFAULT 'open',
        close_reason TEXT,
        exit_price DOUBLE PRECISION,
        close_order_id TEXT,
        close_message TEXT NOT NULL DEFAULT '',
        close_raw_response TEXT NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_predictions_pending ON predictions (actual_result_price, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_trade_orders_prediction ON trade_orders (prediction_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_trade_orders_expiry ON trade_orders (close_status, expires_at)",
    """
    CREATE TABLE IF NOT EXISTS auto_run_logs (
        id BIGSERIAL PRIMARY KEY,
        cycle_started_at TEXT NOT NULL,
        cycle_finished_at TEXT NOT NULL,
        status TEXT NOT NULL,
        interval_seconds INTEGER NOT NULL,
        symbols_json TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        kline_limit INTEGER NOT NULL,
        model_type TEXT NOT NULL,
        execute_paper INTEGER NOT NULL,
        check_accuracy INTEGER NOT NULL,
        predictions_created INTEGER NOT NULL,
        paper_orders_total INTEGER NOT NULL,
        paper_orders_ok INTEGER NOT NULL,
        paper_orders_error INTEGER NOT NULL,
        checked_count INTEGER,
        accurate_count INTEGER,
        direction_accuracy DOUBLE PRECISION,
        overall_checked INTEGER,
        overall_accurate INTEGER,
        overall_accuracy DOUBLE PRECISION,
        error_message TEXT,
        details_json TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_auto_run_logs_started ON auto_run_logs (cycle_started_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS user_advice_actions (
        id BIGSERIAL PRIMARY KEY,
        created_at TEXT NOT NULL,
        symbol TEXT NOT NULL,
        principal DOUBLE PRECISION NOT NULL,
        prediction_id BIGINT REFERENCES predictions(id),
        timeframe TEXT NOT NULL,
        expires_at TEXT,
        suggestion_side TEXT NOT NULL,
        direction TEXT NOT NULL,
        leverage INTEGER NOT NULL,
        margin_amount DOUBLE PRECISION NOT NULL,
        entry_price DOUBLE PRECISION NOT NULL,
        take_profit_price DOUBLE PRECISION NOT NULL,
        stop_loss_price DOUBLE PRECISION NOT NULL,
        notional_value DOUBLE PRECISION NOT NULL,
        expected_profit DOUBLE PRECISION NOT NULL,
        expected_loss DOUBLE PRECISION NOT NULL,
        note TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_advice_actions_created ON user_advice_actions (created_at DESC)",
)
