"""MySQL 8 repository adapter."""

from __future__ import annotations

from crypto_predictor.broker.models import OrderResult
from crypto_predictor.config import MYSQL_DSN
from crypto_predictor.infrastructure.persistence.postgres_repository import PostgreSQLPredictionRepository
from crypto_predictor.models import MarketData, ModelType, Prediction

class MySQLPredictionRepository(PostgreSQLPredictionRepository):
    def __init__(self, dsn: str = MYSQL_DSN):
        self.dsn = dsn

    def init_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                for statement in MYSQL_SCHEMA:
                    cur.execute(statement)
                for statement in MYSQL_MIGRATIONS:
                    try:
                        cur.execute(statement)
                    except Exception as exc:
                        if "Duplicate column" not in str(exc):
                            raise
            conn.commit()

    def _connect(self):
        if not self.dsn:
            raise RuntimeError("MYSQL_DSN is empty; set database.mysql_dsn in config.yaml")
        try:
            import pymysql
            import pymysql.cursors
        except ImportError as exc:
            raise RuntimeError("MySQL backend requires PyMySQL. Install with: pip install PyMySQL>=1.1.0") from exc

        from urllib.parse import parse_qs, unquote, urlparse

        parsed = urlparse(self.dsn)
        if parsed.scheme not in {"mysql", "mysql+pymysql"}:
            raise RuntimeError("MYSQL_DSN must look like mysql://user:password@host:3306/database")
        query = parse_qs(parsed.query)
        charset = query.get("charset", ["utf8mb4"])[0]
        return pymysql.connect(
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 3306,
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            database=(parsed.path or "/").lstrip("/") or None,
            charset=charset,
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def save_prediction(self, market_data: MarketData, prediction: Prediction, model_type: ModelType) -> int:
        from crypto_predictor.market_data import compact_market_data_for_prompt
        from crypto_predictor.time_utils import parse_timeframe_to_timedelta, to_iso, utc_now
        import json

        self.init_schema()
        prediction_time = utc_now()
        expires_at = prediction_time + parse_timeframe_to_timedelta(market_data.timeframe)
        raw_market_data = json.dumps(compact_market_data_for_prompt(market_data), ensure_ascii=False)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO predictions (
                        prediction_time, expires_at, exchange, symbol, timeframe, current_price,
                        prediction_model, prediction_direction, target_price, confidence,
                        position_side, margin_amount, leverage, entry_price, take_profit_price,
                        stop_loss_price, notional_value, expected_profit, expected_loss,
                        risk_reward_ratio, actual_result_price, is_accurate, checked_at, raw_market_data
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, %s)
                    """,
                    (
                        to_iso(prediction_time),
                        to_iso(expires_at),
                        market_data.exchange,
                        market_data.symbol,
                        market_data.timeframe,
                        market_data.current_price,
                        model_type,
                        prediction.direction,
                        prediction.target_price,
                        prediction.confidence,
                        prediction.position_side,
                        prediction.margin_amount,
                        prediction.leverage,
                        prediction.entry_price or market_data.current_price,
                        prediction.take_profit_price,
                        prediction.stop_loss_price,
                        prediction.notional_value or 0.0,
                        prediction.expected_profit or 0.0,
                        prediction.expected_loss or 0.0,
                        prediction.risk_reward_ratio,
                        raw_market_data,
                    ),
                )
                prediction_id = int(cur.lastrowid)
            conn.commit()
        return prediction_id

    def save_trade_order(self, prediction_id: int, result: OrderResult) -> int:
        import json
        from crypto_predictor.time_utils import to_iso, utc_now

        self.init_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT expires_at FROM predictions WHERE id = %s", (prediction_id,))
                prediction = cur.fetchone()
                if prediction is None:
                    raise RuntimeError(f"Prediction not found: {prediction_id}")
                close_status = "open" if result.status not in {"error", "failed", "rejected"} else "error"
                cur.execute(
                    """
                    INSERT INTO trade_orders (
                        prediction_id, created_at, mode, exchange, symbol, side, amount,
                        leverage, status, entry_order_id, take_profit_order_id, stop_loss_order_id,
                        message, raw_response, expires_at, close_status, close_raw_response
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        prediction_id,
                        to_iso(utc_now()),
                        result.mode,
                        result.exchange,
                        result.symbol,
                        result.side,
                        result.amount,
                        result.leverage,
                        result.status,
                        result.entry_order_id,
                        result.take_profit_order_id,
                        result.stop_loss_order_id,
                        result.message,
                        json.dumps(result.raw_response, ensure_ascii=False, default=str),
                        prediction["expires_at"],
                        close_status,
                        "{}",
                    ),
                )
                trade_order_id = int(cur.lastrowid)
            conn.commit()
        return trade_order_id

    def save_auto_run_log(self, payload: dict[str, object]) -> int:
        import json

        self.init_schema()
        symbols = payload.get("symbols", [])
        details = payload.get("details", {})
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO auto_run_logs (
                        cycle_started_at, cycle_finished_at, status, interval_seconds,
                        symbols_json, timeframe, kline_limit, model_type, execute_paper,
                        check_accuracy, predictions_created, paper_orders_total, paper_orders_ok,
                        paper_orders_error, checked_count, accurate_count, direction_accuracy,
                        overall_checked, overall_accurate, overall_accuracy, error_message, details_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(payload.get("cycle_started_at", "")),
                        str(payload.get("cycle_finished_at", "")),
                        str(payload.get("status", "error")),
                        int(payload.get("interval_seconds", 0) or 0),
                        json.dumps(list(symbols), ensure_ascii=False),
                        str(payload.get("timeframe", "")),
                        int(payload.get("kline_limit", 0) or 0),
                        str(payload.get("model_type", "")),
                        1 if payload.get("execute_paper") else 0,
                        1 if payload.get("check_accuracy") else 0,
                        int(payload.get("predictions_created", 0) or 0),
                        int(payload.get("paper_orders_total", 0) or 0),
                        int(payload.get("paper_orders_ok", 0) or 0),
                        int(payload.get("paper_orders_error", 0) or 0),
                        payload.get("checked_count"),
                        payload.get("accurate_count"),
                        payload.get("direction_accuracy"),
                        payload.get("overall_checked"),
                        payload.get("overall_accurate"),
                        payload.get("overall_accuracy"),
                        str(payload.get("error_message", "")),
                        json.dumps(details, ensure_ascii=False, default=str),
                    ),
                )
                log_id = int(cur.lastrowid)
            conn.commit()
        return log_id

    def save_user_advice_action(self, payload: dict[str, object]) -> int:
        from crypto_predictor.time_utils import to_iso, utc_now

        self.init_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_advice_actions (
                        created_at, symbol, principal, prediction_id, timeframe, expires_at,
                        suggestion_side, direction, leverage, margin_amount, entry_price,
                        take_profit_price, stop_loss_price, notional_value, expected_profit,
                        expected_loss, note
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(payload.get("created_at", to_iso(utc_now()))),
                        str(payload.get("symbol", "")),
                        float(payload.get("principal", 0) or 0),
                        payload.get("prediction_id"),
                        str(payload.get("timeframe", "")),
                        payload.get("expires_at"),
                        str(payload.get("suggestion_side", "WAIT")),
                        str(payload.get("direction", "SIDEWAYS")),
                        int(payload.get("leverage", 0) or 0),
                        float(payload.get("margin_amount", 0) or 0),
                        float(payload.get("entry_price", 0) or 0),
                        float(payload.get("take_profit_price", 0) or 0),
                        float(payload.get("stop_loss_price", 0) or 0),
                        float(payload.get("notional_value", 0) or 0),
                        float(payload.get("expected_profit", 0) or 0),
                        float(payload.get("expected_loss", 0) or 0),
                        str(payload.get("note", "")),
                    ),
                )
                action_id = int(cur.lastrowid)
            conn.commit()
        return action_id


MYSQL_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS predictions (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        prediction_time VARCHAR(64) NOT NULL,
        expires_at VARCHAR(64) NOT NULL,
        exchange VARCHAR(64) NOT NULL,
        symbol VARCHAR(64) NOT NULL,
        timeframe VARCHAR(32) NOT NULL,
        current_price DOUBLE NOT NULL,
        prediction_model VARCHAR(64) NOT NULL,
        prediction_direction VARCHAR(32) NOT NULL,
        target_price DOUBLE NOT NULL,
        confidence INT NOT NULL,
        position_side VARCHAR(32) NOT NULL DEFAULT 'NO_TRADE',
        margin_amount DOUBLE NOT NULL DEFAULT 0,
        leverage INT NOT NULL DEFAULT 0,
        entry_price DOUBLE NOT NULL DEFAULT 0,
        take_profit_price DOUBLE NOT NULL DEFAULT 0,
        stop_loss_price DOUBLE NOT NULL DEFAULT 0,
        notional_value DOUBLE NOT NULL DEFAULT 0,
        expected_profit DOUBLE NOT NULL DEFAULT 0,
        expected_loss DOUBLE NOT NULL DEFAULT 0,
        risk_reward_ratio DOUBLE,
        actual_result_price DOUBLE,
        is_accurate INT,
        checked_at VARCHAR(64),
        validation_reason VARCHAR(128),
        validation_event_time VARCHAR(64),
        raw_market_data LONGTEXT NOT NULL,
        INDEX idx_predictions_pending (actual_result_price, expires_at),
        INDEX idx_predictions_time (prediction_time)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_orders (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        prediction_id BIGINT NOT NULL,
        created_at VARCHAR(64) NOT NULL,
        mode VARCHAR(32) NOT NULL,
        exchange VARCHAR(64) NOT NULL,
        symbol VARCHAR(64) NOT NULL,
        side VARCHAR(32) NOT NULL,
        amount DOUBLE NOT NULL,
        leverage INT NOT NULL,
        status VARCHAR(64) NOT NULL,
        entry_order_id VARCHAR(128),
        take_profit_order_id VARCHAR(128),
        stop_loss_order_id VARCHAR(128),
        message VARCHAR(512) NOT NULL,
        raw_response LONGTEXT NOT NULL,
        expires_at VARCHAR(64),
        closed_at VARCHAR(64),
        close_status VARCHAR(32) NOT NULL DEFAULT 'open',
        close_reason VARCHAR(128),
        exit_price DOUBLE,
        close_order_id VARCHAR(128),
        close_message VARCHAR(512) NOT NULL DEFAULT '',
        close_raw_response LONGTEXT NOT NULL,
        CONSTRAINT fk_trade_orders_prediction FOREIGN KEY (prediction_id) REFERENCES predictions(id),
        INDEX idx_trade_orders_prediction (prediction_id, created_at),
        INDEX idx_trade_orders_expiry (close_status, expires_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS auto_run_logs (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        cycle_started_at VARCHAR(64) NOT NULL,
        cycle_finished_at VARCHAR(64) NOT NULL,
        status VARCHAR(64) NOT NULL,
        interval_seconds INT NOT NULL,
        symbols_json LONGTEXT NOT NULL,
        timeframe VARCHAR(32) NOT NULL,
        kline_limit INT NOT NULL,
        model_type VARCHAR(64) NOT NULL,
        execute_paper INT NOT NULL,
        check_accuracy INT NOT NULL,
        predictions_created INT NOT NULL,
        paper_orders_total INT NOT NULL,
        paper_orders_ok INT NOT NULL,
        paper_orders_error INT NOT NULL,
        checked_count INT,
        accurate_count INT,
        direction_accuracy DOUBLE,
        overall_checked INT,
        overall_accurate INT,
        overall_accuracy DOUBLE,
        error_message VARCHAR(1024),
        details_json LONGTEXT NOT NULL,
        INDEX idx_auto_run_logs_started (cycle_started_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS user_advice_actions (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        created_at VARCHAR(64) NOT NULL,
        symbol VARCHAR(64) NOT NULL,
        principal DOUBLE NOT NULL,
        prediction_id BIGINT,
        timeframe VARCHAR(32) NOT NULL,
        expires_at VARCHAR(64),
        suggestion_side VARCHAR(32) NOT NULL,
        direction VARCHAR(32) NOT NULL,
        leverage INT NOT NULL,
        margin_amount DOUBLE NOT NULL,
        entry_price DOUBLE NOT NULL,
        take_profit_price DOUBLE NOT NULL,
        stop_loss_price DOUBLE NOT NULL,
        notional_value DOUBLE NOT NULL,
        expected_profit DOUBLE NOT NULL,
        expected_loss DOUBLE NOT NULL,
        note VARCHAR(1024) NOT NULL DEFAULT '',
        CONSTRAINT fk_user_advice_prediction FOREIGN KEY (prediction_id) REFERENCES predictions(id),
        INDEX idx_user_advice_actions_created (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
)


MYSQL_MIGRATIONS = (
    "ALTER TABLE predictions ADD COLUMN validation_reason VARCHAR(128)",
    "ALTER TABLE predictions ADD COLUMN validation_event_time VARCHAR(64)",
)
