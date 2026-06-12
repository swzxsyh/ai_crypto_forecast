"""Persistence repository boundary."""

from __future__ import annotations

from typing import Any, Protocol

from crypto_predictor.broker.models import OrderResult
from crypto_predictor.config import DB_BACKEND, DB_PATH, MYSQL_DSN, POSTGRES_DSN
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
    def get_next_pending_prediction_expiry(self) -> str | None: ...
    def list_expired_pending_predictions(self, now_iso: str) -> list[Any]: ...
    def update_prediction_accuracy(
        self,
        prediction_id: int,
        actual_price: float,
        is_accurate: bool,
        checked_at: str,
    ) -> None: ...
    def list_expired_open_trade_orders(self, now_iso: str) -> list[Any]: ...
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
    ) -> None:
        from crypto_predictor.database import get_connection, init_db

        init_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE predictions
                SET actual_result_price = ?,
                    is_accurate = ?,
                    checked_at = ?
                WHERE id = ?
                """,
                (actual_price, 1 if is_accurate else 0, checked_at, prediction_id),
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


class PostgreSQLPredictionRepository:
    def __init__(self, dsn: str = POSTGRES_DSN):
        self.dsn = dsn

    def init_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                for statement in POSTGRES_SCHEMA:
                    cur.execute(statement)
            conn.commit()

    def _connect(self):
        if not self.dsn:
            raise RuntimeError("POSTGRES_DSN is empty; set database.postgres_dsn in config.yaml")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL backend requires psycopg. Install with: pip install 'psycopg[binary]>=3.1'") from exc
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def _fetchone(self, query: str, params: tuple[object, ...] = ()) -> Any | None:
        self.init_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchone()

    def _fetchall(self, query: str, params: tuple[object, ...] = ()) -> list[Any]:
        self.init_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return list(cur.fetchall())

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
                    RETURNING id
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
                row = cur.fetchone()
            conn.commit()
        return int(row["id"])

    def count_predictions(self) -> int:
        row = self._fetchone("SELECT COUNT(*) AS total FROM predictions")
        return int(row["total"] or 0)

    def list_recent_predictions(self, limit: int = 50, offset: int = 0) -> list[Any]:
        return self._fetchall(
            """
            SELECT *
            FROM predictions
            ORDER BY prediction_time DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )

    def get_prediction_by_id(self, prediction_id: int | None) -> Any | None:
        if prediction_id is None:
            return None
        return self._fetchone("SELECT * FROM predictions WHERE id = %s", (prediction_id,))

    def get_latest_prediction(self) -> Any | None:
        return self._fetchone("SELECT * FROM predictions ORDER BY prediction_time DESC LIMIT 1")

    def get_latest_prediction_for_symbol(self, symbol: str) -> Any | None:
        return self._fetchone(
            "SELECT * FROM predictions WHERE symbol = %s ORDER BY prediction_time DESC LIMIT 1",
            (symbol,),
        )

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
                    RETURNING id
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
                row = cur.fetchone()
            conn.commit()
        return int(row["id"])

    def list_recent_trade_orders(self, limit: int = 50) -> list[Any]:
        return self._fetchall(
            """
            SELECT trade_orders.*, predictions.position_side, predictions.margin_amount,
                   predictions.expires_at AS prediction_expires_at
            FROM trade_orders
            JOIN predictions ON predictions.id = trade_orders.prediction_id
            ORDER BY trade_orders.created_at DESC
            LIMIT %s
            """,
            (limit,),
        )

    def get_next_open_trade_order_expiry(self) -> str | None:
        row = self._fetchone(
            """
            SELECT MIN(expires_at) AS next_expires_at
            FROM trade_orders
            WHERE close_status = 'open'
              AND expires_at IS NOT NULL
            """
        )
        return row["next_expires_at"] if row and row["next_expires_at"] else None

    def update_trade_order_close(self, order_id: int, payload: dict[str, object]) -> None:
        import json
        from crypto_predictor.time_utils import to_iso, utc_now

        self.init_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE trade_orders
                    SET closed_at = %s,
                        close_status = %s,
                        close_reason = %s,
                        exit_price = %s,
                        close_order_id = %s,
                        close_message = %s,
                        close_raw_response = %s
                    WHERE id = %s
                    """,
                    (
                        str(payload.get("closed_at") or to_iso(utc_now())),
                        str(payload.get("close_status") or "closed"),
                        payload.get("close_reason"),
                        payload.get("exit_price"),
                        payload.get("close_order_id"),
                        str(payload.get("close_message") or ""),
                        json.dumps(payload.get("close_raw_response") or {}, ensure_ascii=False, default=str),
                        order_id,
                    ),
                )
            conn.commit()

    def get_next_pending_prediction_expiry(self) -> str | None:
        row = self._fetchone(
            """
            SELECT MIN(expires_at) AS next_expires_at
            FROM predictions
            WHERE actual_result_price IS NULL
            """
        )
        return row["next_expires_at"] if row and row["next_expires_at"] else None

    def list_expired_pending_predictions(self, now_iso: str) -> list[Any]:
        return self._fetchall(
            """
            SELECT *
            FROM predictions
            WHERE actual_result_price IS NULL
              AND expires_at <= %s
            ORDER BY expires_at ASC
            """,
            (now_iso,),
        )

    def update_prediction_accuracy(
        self,
        prediction_id: int,
        actual_price: float,
        is_accurate: bool,
        checked_at: str,
    ) -> None:
        self.init_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE predictions
                    SET actual_result_price = %s,
                        is_accurate = %s,
                        checked_at = %s
                    WHERE id = %s
                    """,
                    (actual_price, 1 if is_accurate else 0, checked_at, prediction_id),
                )
            conn.commit()

    def list_expired_open_trade_orders(self, now_iso: str) -> list[Any]:
        return self._fetchall(
            """
            SELECT trade_orders.*, predictions.position_side, predictions.expires_at AS prediction_expires_at
            FROM trade_orders
            JOIN predictions ON predictions.id = trade_orders.prediction_id
            WHERE trade_orders.close_status = 'open'
              AND trade_orders.expires_at IS NOT NULL
              AND trade_orders.expires_at <= %s
            ORDER BY trade_orders.expires_at ASC
            """,
            (now_iso,),
        )
    def list_chart_predictions(
        self,
        symbol: str | None = None,
        limit: int = 100,
        start_utc: str | None = None,
        end_utc: str | None = None,
    ) -> list[Any]:
        filters: list[str] = []
        params: list[object] = []
        if symbol:
            filters.append("symbol = %s")
            params.append(symbol)
        if start_utc:
            filters.append("prediction_time >= %s")
            params.append(start_utc)
        if end_utc:
            filters.append("prediction_time < %s")
            params.append(end_utc)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        rows = self._fetchall(
            f"""
            SELECT *
            FROM predictions
            {where_clause}
            ORDER BY prediction_time DESC
            LIMIT %s
            """,
            tuple(params),
        )
        return list(reversed(rows))

    def get_overall_accuracy(self) -> dict[str, object]:
        row = self._fetchone(
            """
            SELECT COUNT(*) AS total_checked,
                   SUM(CASE WHEN is_accurate = 1 THEN 1 ELSE 0 END) AS total_accurate
            FROM predictions
            WHERE is_accurate IS NOT NULL
            """
        )
        total_checked = int(row["total_checked"] or 0)
        total_accurate = int(row["total_accurate"] or 0)
        return {
            "total_checked": total_checked,
            "total_accurate": total_accurate,
            "overall_accuracy": (total_accurate / total_checked) if total_checked else None,
        }

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
                    RETURNING id
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
                row = cur.fetchone()
            conn.commit()
        return int(row["id"])

    def count_auto_run_logs(self) -> int:
        row = self._fetchone("SELECT COUNT(*) AS total FROM auto_run_logs")
        return int(row["total"] or 0)

    def list_recent_auto_run_logs(self, limit: int = 50, offset: int = 0) -> list[Any]:
        return self._fetchall(
            """
            SELECT *
            FROM auto_run_logs
            ORDER BY cycle_started_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )

    def get_auto_run_log_stats(self) -> dict[str, object]:
        row = self._fetchone(
            """
            SELECT COUNT(*) AS total_cycles,
                   SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS ok_cycles,
                   SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) AS error_cycles,
                   MAX(cycle_started_at) AS last_cycle_started_at,
                   MAX(cycle_finished_at) AS last_cycle_finished_at,
                   AVG(CASE WHEN direction_accuracy IS NOT NULL THEN direction_accuracy END) AS avg_direction_accuracy
            FROM auto_run_logs
            """
        )
        return {
            "total_cycles": int(row["total_cycles"] or 0),
            "ok_cycles": int(row["ok_cycles"] or 0),
            "error_cycles": int(row["error_cycles"] or 0),
            "last_cycle_started_at": row["last_cycle_started_at"],
            "last_cycle_finished_at": row["last_cycle_finished_at"],
            "avg_direction_accuracy": row["avg_direction_accuracy"],
        }

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
                    RETURNING id
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
                row = cur.fetchone()
            conn.commit()
        return int(row["id"])

    def list_recent_user_advice_actions(self, limit: int = 50) -> list[Any]:
        return self._fetchall(
            """
            SELECT *
            FROM user_advice_actions
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )


class MySQLPredictionRepository(PostgreSQLPredictionRepository):
    def __init__(self, dsn: str = MYSQL_DSN):
        self.dsn = dsn

    def init_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                for statement in MYSQL_SCHEMA:
                    cur.execute(statement)
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


def get_repository() -> PredictionRepository:
    if DB_BACKEND == "postgresql":
        return PostgreSQLPredictionRepository()
    if DB_BACKEND == "mysql":
        return MySQLPredictionRepository()
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
