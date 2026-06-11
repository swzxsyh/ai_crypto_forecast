"""SQLite 数据库访问层。"""

from __future__ import annotations

import json
import sqlite3
from typing import Iterable

from crypto_predictor.broker.models import OrderResult
from crypto_predictor.config import DB_PATH
from crypto_predictor.market_data import compact_market_data_for_prompt
from crypto_predictor.models import MarketData, ModelType, Prediction
from crypto_predictor.time_utils import parse_timeframe_to_timedelta, to_iso, utc_now


CONTRACT_COLUMNS: dict[str, str] = {
    "position_side": "TEXT NOT NULL DEFAULT 'NO_TRADE'",
    "margin_amount": "REAL NOT NULL DEFAULT 0",
    "leverage": "INTEGER NOT NULL DEFAULT 0",
    "entry_price": "REAL NOT NULL DEFAULT 0",
    "take_profit_price": "REAL NOT NULL DEFAULT 0",
    "stop_loss_price": "REAL NOT NULL DEFAULT 0",
    "notional_value": "REAL NOT NULL DEFAULT 0",
    "expected_profit": "REAL NOT NULL DEFAULT 0",
    "expected_loss": "REAL NOT NULL DEFAULT 0",
    "risk_reward_ratio": "REAL",
}


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """创建 SQLite 连接，并让查询结果可以通过字段名访问。"""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """初始化数据库表，并对旧表补齐新增字段。"""

    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_time TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                current_price REAL NOT NULL,
                prediction_model TEXT NOT NULL,
                prediction_direction TEXT NOT NULL,
                target_price REAL NOT NULL,
                confidence INTEGER NOT NULL,
                position_side TEXT NOT NULL DEFAULT 'NO_TRADE',
                margin_amount REAL NOT NULL DEFAULT 0,
                leverage INTEGER NOT NULL DEFAULT 0,
                entry_price REAL NOT NULL DEFAULT 0,
                take_profit_price REAL NOT NULL DEFAULT 0,
                stop_loss_price REAL NOT NULL DEFAULT 0,
                notional_value REAL NOT NULL DEFAULT 0,
                expected_profit REAL NOT NULL DEFAULT 0,
                expected_loss REAL NOT NULL DEFAULT 0,
                risk_reward_ratio REAL,
                actual_result_price REAL,
                is_accurate INTEGER,
                checked_at TEXT,
                raw_market_data TEXT NOT NULL
            )
            """
        )
        ensure_contract_columns(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                mode TEXT NOT NULL,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                amount REAL NOT NULL,
                leverage INTEGER NOT NULL,
                status TEXT NOT NULL,
                entry_order_id TEXT,
                take_profit_order_id TEXT,
                stop_loss_order_id TEXT,
                message TEXT NOT NULL,
                raw_response TEXT NOT NULL,
                FOREIGN KEY (prediction_id) REFERENCES predictions (id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_predictions_pending
            ON predictions (actual_result_price, expires_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trade_orders_prediction
            ON trade_orders (prediction_id, created_at)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auto_run_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                direction_accuracy REAL,
                overall_checked INTEGER,
                overall_accurate INTEGER,
                overall_accuracy REAL,
                error_message TEXT,
                details_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_auto_run_logs_started
            ON auto_run_logs (cycle_started_at DESC)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_advice_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                principal REAL NOT NULL,
                prediction_id INTEGER,
                timeframe TEXT NOT NULL,
                expires_at TEXT,
                suggestion_side TEXT NOT NULL,
                direction TEXT NOT NULL,
                leverage INTEGER NOT NULL,
                margin_amount REAL NOT NULL,
                entry_price REAL NOT NULL,
                take_profit_price REAL NOT NULL,
                stop_loss_price REAL NOT NULL,
                notional_value REAL NOT NULL,
                expected_profit REAL NOT NULL,
                expected_loss REAL NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (prediction_id) REFERENCES predictions (id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_advice_actions_created
            ON user_advice_actions (created_at DESC)
            """
        )
        conn.commit()


def ensure_contract_columns(conn: sqlite3.Connection) -> None:
    """给旧版本数据库表补齐合约字段。"""

    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(predictions)").fetchall()}
    for column_name, column_type in CONTRACT_COLUMNS.items():
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE predictions ADD COLUMN {column_name} {column_type}")


def save_prediction(
    market_data: MarketData,
    prediction: Prediction,
    model_type: ModelType,
    db_path: str = DB_PATH,
) -> int:
    """将一次预测写入数据库，返回新记录 ID。"""

    init_db(db_path)

    prediction_time = utc_now()
    expires_at = prediction_time + parse_timeframe_to_timedelta(market_data.timeframe)
    raw_market_data = json.dumps(compact_market_data_for_prompt(market_data), ensure_ascii=False)

    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO predictions (
                prediction_time,
                expires_at,
                exchange,
                symbol,
                timeframe,
                current_price,
                prediction_model,
                prediction_direction,
                target_price,
                confidence,
                position_side,
                margin_amount,
                leverage,
                entry_price,
                take_profit_price,
                stop_loss_price,
                notional_value,
                expected_profit,
                expected_loss,
                risk_reward_ratio,
                actual_result_price,
                is_accurate,
                checked_at,
                raw_market_data
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?)
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
        conn.commit()
        return int(cursor.lastrowid)


def iter_expired_pending_predictions(
    conn: sqlite3.Connection,
    now_iso: str,
) -> Iterable[sqlite3.Row]:
    """查询已到期且尚未回填 actual_result_price 的预测记录。"""

    return conn.execute(
        """
        SELECT *
        FROM predictions
        WHERE actual_result_price IS NULL
          AND expires_at <= ?
        ORDER BY expires_at ASC
        """,
        (now_iso,),
    ).fetchall()


def count_predictions(db_path: str = DB_PATH) -> int:
    """Return the total number of prediction records."""

    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM predictions").fetchone()
    return int(row["total"] or 0)


def list_recent_predictions(db_path: str = DB_PATH, limit: int = 50, offset: int = 0) -> list[sqlite3.Row]:
    """查询最近的预测记录，供 Web 看板使用。"""

    init_db(db_path)
    with get_connection(db_path) as conn:
        return conn.execute(
            """
            SELECT *
            FROM predictions
            ORDER BY prediction_time DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()


def get_prediction_by_id(prediction_id: int | None, db_path: str = DB_PATH) -> sqlite3.Row | None:
    """按 ID 查询预测记录。"""

    if prediction_id is None:
        return None

    init_db(db_path)
    with get_connection(db_path) as conn:
        return conn.execute(
            """
            SELECT *
            FROM predictions
            WHERE id = ?
            """,
            (prediction_id,),
        ).fetchone()


def get_latest_prediction(db_path: str = DB_PATH) -> sqlite3.Row | None:
    """查询最新一条预测记录。"""

    init_db(db_path)
    with get_connection(db_path) as conn:
        return conn.execute(
            """
            SELECT *
            FROM predictions
            ORDER BY prediction_time DESC
            LIMIT 1
            """
        ).fetchone()


def get_latest_prediction_for_symbol(symbol: str, db_path: str = DB_PATH) -> sqlite3.Row | None:
    """按交易对查询最近一条预测记录。"""

    init_db(db_path)
    with get_connection(db_path) as conn:
        return conn.execute(
            """
            SELECT *
            FROM predictions
            WHERE symbol = ?
            ORDER BY prediction_time DESC
            LIMIT 1
            """,
            (symbol,),
        ).fetchone()


def save_trade_order(prediction_id: int, result: OrderResult, db_path: str = DB_PATH) -> int:
    """保存模拟或真实订单执行结果。"""

    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO trade_orders (
                prediction_id,
                created_at,
                mode,
                exchange,
                symbol,
                side,
                amount,
                leverage,
                status,
                entry_order_id,
                take_profit_order_id,
                stop_loss_order_id,
                message,
                raw_response
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_recent_trade_orders(db_path: str = DB_PATH, limit: int = 50) -> list[sqlite3.Row]:
    """查询最近订单记录。"""

    init_db(db_path)
    with get_connection(db_path) as conn:
        return conn.execute(
            """
            SELECT trade_orders.*, predictions.position_side, predictions.margin_amount
            FROM trade_orders
            JOIN predictions ON predictions.id = trade_orders.prediction_id
            ORDER BY trade_orders.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def list_chart_predictions(
    db_path: str = DB_PATH,
    symbol: str | None = None,
    limit: int = 100,
    start_utc: str | None = None,
    end_utc: str | None = None,
) -> list[sqlite3.Row]:
    """查询图表需要的预测记录，按时间正序返回。"""

    init_db(db_path)
    with get_connection(db_path) as conn:
        filters: list[str] = []
        params: list[object] = []
        if symbol:
            filters.append("symbol = ?")
            params.append(symbol)
        if start_utc:
            filters.append("prediction_time >= ?")
            params.append(start_utc)
        if end_utc:
            filters.append("prediction_time < ?")
            params.append(end_utc)

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT *
            FROM predictions
            {where_clause}
            ORDER BY prediction_time DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return list(reversed(rows))


def get_overall_accuracy(db_path: str = DB_PATH) -> dict[str, object]:
    """汇总数据库里所有已验证预测的方向准确率。"""

    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_checked,
                SUM(CASE WHEN is_accurate = 1 THEN 1 ELSE 0 END) AS total_accurate
            FROM predictions
            WHERE is_accurate IS NOT NULL
            """
        ).fetchone()

    total_checked = int(row["total_checked"] or 0)
    total_accurate = int(row["total_accurate"] or 0)
    overall_accuracy = (total_accurate / total_checked) if total_checked else None

    return {
        "total_checked": total_checked,
        "total_accurate": total_accurate,
        "overall_accuracy": overall_accuracy,
    }


def save_auto_run_log(payload: dict[str, object], db_path: str = DB_PATH) -> int:
    """保存自动任务每轮执行日志。"""

    init_db(db_path)

    symbols = payload.get("symbols", [])
    details = payload.get("details", {})

    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO auto_run_logs (
                cycle_started_at,
                cycle_finished_at,
                status,
                interval_seconds,
                symbols_json,
                timeframe,
                kline_limit,
                model_type,
                execute_paper,
                check_accuracy,
                predictions_created,
                paper_orders_total,
                paper_orders_ok,
                paper_orders_error,
                checked_count,
                accurate_count,
                direction_accuracy,
                overall_checked,
                overall_accurate,
                overall_accuracy,
                error_message,
                details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        conn.commit()
        return int(cursor.lastrowid)


def count_auto_run_logs(db_path: str = DB_PATH) -> int:
    """Return the total number of auto task log records."""

    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM auto_run_logs").fetchone()
    return int(row["total"] or 0)


def list_recent_auto_run_logs(db_path: str = DB_PATH, limit: int = 50, offset: int = 0) -> list[sqlite3.Row]:
    """查询最近自动任务日志。"""

    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM auto_run_logs
            ORDER BY cycle_started_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return rows


def get_auto_run_log_stats(db_path: str = DB_PATH) -> dict[str, object]:
    """汇总自动任务运行情况。"""

    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_cycles,
                SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS ok_cycles,
                SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) AS error_cycles,
                MAX(cycle_started_at) AS last_cycle_started_at,
                MAX(cycle_finished_at) AS last_cycle_finished_at,
                AVG(CASE WHEN direction_accuracy IS NOT NULL THEN direction_accuracy END) AS avg_direction_accuracy
            FROM auto_run_logs
            """
        ).fetchone()

    total_cycles = int(row["total_cycles"] or 0)
    ok_cycles = int(row["ok_cycles"] or 0)
    error_cycles = int(row["error_cycles"] or 0)

    return {
        "total_cycles": total_cycles,
        "ok_cycles": ok_cycles,
        "error_cycles": error_cycles,
        "last_cycle_started_at": row["last_cycle_started_at"],
        "last_cycle_finished_at": row["last_cycle_finished_at"],
        "avg_direction_accuracy": row["avg_direction_accuracy"],
    }


def save_user_advice_action(payload: dict[str, object], db_path: str = DB_PATH) -> int:
    """保存用户建议操作记录。"""

    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO user_advice_actions (
                created_at,
                symbol,
                principal,
                prediction_id,
                timeframe,
                expires_at,
                suggestion_side,
                direction,
                leverage,
                margin_amount,
                entry_price,
                take_profit_price,
                stop_loss_price,
                notional_value,
                expected_profit,
                expected_loss,
                note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        conn.commit()
        return int(cursor.lastrowid)


def list_recent_user_advice_actions(db_path: str = DB_PATH, limit: int = 50) -> list[sqlite3.Row]:
    """查询最近的用户建议操作记录。"""

    init_db(db_path)
    with get_connection(db_path) as conn:
        return conn.execute(
            """
            SELECT *
            FROM user_advice_actions
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
