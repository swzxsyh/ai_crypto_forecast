"""本地 Web 看板。"""

from __future__ import annotations

import os
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from crypto_predictor.advice import build_advice_from_prediction
from crypto_predictor.auto_task_manager import AutoTaskConfig, AutoTaskManager, build_default_auto_config
from crypto_predictor.config import (
    AUTO_RUN_ENABLED,
    ENABLE_LIVE_TRADING,
    LIVE_CONFIRM_TEXT,
    WEB_AUTO_REFRESH_SECONDS,
    WEB_DEFAULT_TIMEZONE,
    WEB_SECRET_KEY,
    WEB_TIMEZONE_OPTIONS,
)
from crypto_predictor.broker.executor import execute_prediction_order
from crypto_predictor.config import DEFAULT_LIMIT, DEFAULT_SYMBOLS, DEFAULT_TIMEFRAME, DEFAULT_TIMEFRAMES
from crypto_predictor.database import (
    count_auto_run_logs,
    count_predictions,
    get_auto_run_log_stats,
    get_latest_prediction_for_symbol,
    get_overall_accuracy,
    list_chart_predictions,
    list_recent_auto_run_logs,
    list_recent_predictions,
    list_recent_trade_orders,
    list_recent_user_advice_actions,
    save_user_advice_action,
)
from crypto_predictor.i18n import SUPPORTED_LANGUAGES, normalize_language, translate
from crypto_predictor.infrastructure.database_backends import get_database_backend
from crypto_predictor.infrastructure.task_status import default_task_status_store
from crypto_predictor.service import run_prediction_once, run_predictions_for_symbols
from crypto_predictor.time_utils import from_iso, to_iso, utc_now
from crypto_predictor.validator import check_and_update_accuracy


def resolve_timezone_options() -> tuple[str, ...]:
    """过滤无效时区配置，避免页面出现非法值。"""

    valid: list[str] = []
    for item in WEB_TIMEZONE_OPTIONS:
        try:
            ZoneInfo(item)
            valid.append(item)
        except Exception:  # noqa: BLE001
            continue

    if not valid:
        return ("UTC", "Asia/Shanghai")
    return tuple(valid)


TIMEZONE_OPTIONS = resolve_timezone_options()
DEFAULT_TIMEZONE = WEB_DEFAULT_TIMEZONE if WEB_DEFAULT_TIMEZONE in TIMEZONE_OPTIONS else TIMEZONE_OPTIONS[0]
PREDICTIONS_PAGE_SIZE = 25
AUTO_LOGS_PAGE_SIZE = 20


def create_app() -> Flask:
    """创建 Flask 应用。"""

    app = Flask(__name__)
    app.secret_key = WEB_SECRET_KEY
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.jinja_env.auto_reload = True
    manager = AutoTaskManager()
    app.extensions["auto_task_manager"] = manager
    maybe_start_auto_worker(app, manager)

    def current_timezone() -> str:
        candidate = session.get("dashboard_timezone", DEFAULT_TIMEZONE)
        if candidate not in TIMEZONE_OPTIONS:
            return DEFAULT_TIMEZONE
        return candidate

    def current_language() -> str:
        return normalize_language(session.get("dashboard_language"))

    @app.context_processor
    def inject_i18n():
        language = current_language()
        return {
            "current_language": language,
            "language_options": SUPPORTED_LANGUAGES,
            "t": lambda key, **kwargs: translate(language, key, **kwargs),
        }

    def parse_auto_config_from_form() -> AutoTaskConfig:
        interval_seconds = int(request.form.get("interval_seconds", "3600"))
        max_cycles = int(request.form.get("max_cycles", "0") or "0")
        timeframe = request.form.get("timeframe", DEFAULT_TIMEFRAME).strip() or DEFAULT_TIMEFRAME
        limit = int(request.form.get("limit", str(DEFAULT_LIMIT)))
        model_type = request.form.get("model_type", "openai").strip() or "openai"
        execute_paper = request.form.get("execute_paper") == "on"
        execute_live = request.form.get("execute_live") == "on"
        check_accuracy = request.form.get("check_accuracy") == "on"
        allow_overlap = request.form.get("allow_overlap") == "on"

        max_margin_raw = request.form.get("max_margin_per_trade", "").strip()
        max_margin_per_trade = float(max_margin_raw) if max_margin_raw else None

        symbols_preset = request.form.get("symbols_preset", "all").strip()
        symbols_custom = request.form.get("symbols_custom", "").strip()

        if symbols_preset == "all":
            symbols = DEFAULT_SYMBOLS
        elif symbols_preset == "custom":
            parsed = tuple(s.strip() for s in symbols_custom.split(",") if s.strip())
            symbols = parsed or (DEFAULT_SYMBOLS[0],)
        else:
            # single symbol selected from dropdown
            symbols = (symbols_preset,) if symbols_preset else DEFAULT_SYMBOLS

        return AutoTaskConfig(
            interval_seconds=interval_seconds,
            max_cycles=max_cycles,
            symbols=symbols,
            timeframe=timeframe,
            limit=limit,
            model_type=model_type,
            execute_paper=execute_paper,
            execute_live=execute_live,
            check_accuracy=check_accuracy,
            max_margin_per_trade=max_margin_per_trade,
            allow_overlap=allow_overlap,
        )

    def parse_advice_form_inputs() -> tuple[str, float, str]:
        symbol = request.form.get("symbol", "").strip()
        
        # 处理自定义货币对
        if symbol == "custom":
            symbol = request.form.get("symbol_custom", "").strip()
            if not symbol:
                raise ValueError("请输入自定义交易对（例：XRP/USDT）")
        
        if not symbol:
            raise ValueError("请先选择币种")

        principal_text = request.form.get("principal", "").strip()
        principal = float(principal_text)
        if principal <= 0:
            raise ValueError("本金必须大于 0")

        note = request.form.get("note", "").strip()
        return symbol, principal, note

    def render_dashboard_page(
        suggestion_preview: dict[str, object] | None = None,
        advice_form: dict[str, object] | None = None,
    ):
        return render_template(
            "pages/dashboard.html",
            **build_dashboard_context(suggestion_preview=suggestion_preview, advice_form=advice_form),
        )

    def build_dashboard_context(
        suggestion_preview: dict[str, object] | None = None,
        advice_form: dict[str, object] | None = None,
    ) -> dict[str, object]:
        stats = get_overall_accuracy()
        auto_log_stats = get_auto_run_log_stats()
        predictions_pagination = build_pagination("predictions_page", PREDICTIONS_PAGE_SIZE, count_predictions())
        auto_logs_pagination = build_pagination("auto_logs_page", AUTO_LOGS_PAGE_SIZE, count_auto_run_logs())
        auto_logs = list_recent_auto_run_logs(
            limit=auto_logs_pagination["page_size"],
            offset=auto_logs_pagination["offset"],
        )
        rows = list_recent_predictions(
            limit=predictions_pagination["page_size"],
            offset=predictions_pagination["offset"],
        )
        trade_orders = list_recent_trade_orders(limit=30)
        advice_actions = list_recent_user_advice_actions(limit=30)
        return {
            "stats": stats,
            "auto_status": manager.get_status(),
            "auto_log_stats": auto_log_stats,
            "auto_logs": auto_logs,
            "auto_logs_pagination": auto_logs_pagination,
            "rows": rows,
            "predictions_pagination": predictions_pagination,
            "trade_orders": trade_orders,
            "advice_actions": advice_actions,
            "suggestion_preview": suggestion_preview,
            "advice_form": advice_form or {},
            "symbols": DEFAULT_SYMBOLS,
            "default_timeframe": DEFAULT_TIMEFRAME,
            "timeframes": DEFAULT_TIMEFRAMES,
            "default_limit": DEFAULT_LIMIT,
            "web_auto_refresh_seconds": WEB_AUTO_REFRESH_SECONDS,
            "selected_timezone": current_timezone(),
            "timezone_options": TIMEZONE_OPTIONS,
            "current_language": current_language(),
            "language_options": SUPPORTED_LANGUAGES,
            "page_url": page_url,
        }

    @app.get("/")
    def dashboard():
        return render_dashboard_page()

    @app.get("/api/dashboard-fragments")
    def dashboard_fragments():
        context = build_dashboard_context()
        return jsonify(
            {
                "stats": render_template("partials/stats_cards.html", **context),
                "predictions": render_template("partials/predictions_table.html", **context),
                "orders": render_template("partials/orders_table.html", **context),
                "auto": render_template("partials/auto_control_panel.html", **context),
                "advice": render_template("partials/advice_panel.html", **context),
            }
        )

    @app.get("/api/system-status")
    def system_status():
        return jsonify(
            {
                "database": get_database_backend().describe(),
                "tasks": [status.__dict__ for status in default_task_status_store.all()],
            }
        )

    @app.post("/settings/timezone")
    def update_timezone():
        timezone = request.form.get("timezone", "").strip()
        if timezone in TIMEZONE_OPTIONS:
            session["dashboard_timezone"] = timezone
            flash(f"时区已切换为 {timezone}", "success")
        else:
            flash("时区配置无效", "error")
        return redirect(url_for("dashboard"))

    @app.post("/settings/language")
    def update_language():
        session["dashboard_language"] = normalize_language(request.form.get("language", "").strip())
        return redirect(url_for("dashboard"))

    @app.post("/auto/toggle")
    def auto_toggle():
        payload: dict[str, object] = {"ok": False}
        try:
            if manager.get_status().get("running"):
                result = manager.stop()
                payload = {"ok": bool(result.get("stopped")), "action": "stop", "result": result}
                if result.get("stopped"):
                    flash("自动任务已停止。", "success")
                else:
                    flash("自动任务当前未运行。", "error")
            else:
                start_result = manager.start(parse_auto_config_from_form())
                payload = {"ok": bool(start_result.get("started")), "action": "start", "result": start_result}
                if start_result.get("started"):
                    flash("自动任务已启动。", "success")
                else:
                    flash("自动任务已在运行中。", "error")
        except Exception as exc:
            payload = {"ok": False, "error": format_user_error(exc)}
            flash(format_user_error(exc), "error")
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify(payload)
        return redirect(url_for("dashboard"))

    @app.post("/advice/preview")
    def advice_preview():
        try:
            symbol, principal, note = parse_advice_form_inputs()
            prediction = get_latest_prediction_for_symbol(symbol)
            if prediction is None:
                flash(f"{symbol} 暂无预测记录，请先创建预测。", "error")
                return redirect(url_for("dashboard"))

            suggestion = build_advice_from_prediction(prediction, principal)
            return render_dashboard_page(
                suggestion_preview=suggestion,
                advice_form={"symbol": symbol, "principal": principal, "note": note},
            )
        except Exception as exc:
            flash(format_user_error(exc), "error")
            return redirect(url_for("dashboard"))

    @app.post("/advice/record")
    def advice_record():
        try:
            symbol, principal, note = parse_advice_form_inputs()
            prediction = get_latest_prediction_for_symbol(symbol)
            if prediction is None:
                flash(f"{symbol} 暂无预测记录，请先创建预测。", "error")
                return redirect(url_for("dashboard"))

            suggestion = build_advice_from_prediction(prediction, principal)
            advice_id = save_user_advice_action(
                {
                    "created_at": to_iso(utc_now()),
                    "symbol": suggestion["symbol"],
                    "principal": suggestion["principal"],
                    "prediction_id": suggestion["prediction_id"],
                    "timeframe": suggestion["timeframe"],
                    "expires_at": suggestion["expires_at"],
                    "suggestion_side": suggestion["suggestion_side"],
                    "direction": suggestion["direction"],
                    "leverage": suggestion["leverage"],
                    "margin_amount": suggestion["margin_amount"],
                    "entry_price": suggestion["entry_price"],
                    "take_profit_price": suggestion["take_profit_price"],
                    "stop_loss_price": suggestion["stop_loss_price"],
                    "notional_value": suggestion["notional_value"],
                    "expected_profit": suggestion["expected_profit"],
                    "expected_loss": suggestion["expected_loss"],
                    "note": note,
                }
            )
            flash(f"建议已记录（ID={advice_id}）。", "success")
        except Exception as exc:
            flash(format_user_error(exc), "error")
        return redirect(url_for("dashboard"))

    @app.post("/predict")
    def predict():
        all_symbols = request.form.get("all_symbols") == "on"
        symbol = request.form.get("symbol", "").strip()
        
        # 处理自定义货币对
        if symbol == "custom":
            symbol = request.form.get("symbol_custom", "").strip()
            if not symbol:
                flash("请输入自定义交易对（例：XRP/USDT）", "error")
                return redirect(url_for("dashboard"))
        
        timeframe = request.form.get("timeframe", DEFAULT_TIMEFRAME).strip() or DEFAULT_TIMEFRAME
        limit = int(request.form.get("limit", DEFAULT_LIMIT))
        model_type = request.form.get("model_type", "openai")

        try:
            if all_symbols:
                run_predictions_for_symbols(DEFAULT_SYMBOLS, timeframe=timeframe, limit=limit, model_type=model_type)
            else:
                if not symbol:
                    flash("请选择或输入交易对", "error")
                    return redirect(url_for("dashboard"))
                run_prediction_once(symbol=symbol, timeframe=timeframe, limit=limit, model_type=model_type)
            flash("预测已创建。", "success")
        except Exception as exc:
            flash(format_user_error(exc), "error")

        return redirect(url_for("dashboard"))

    @app.post("/check")
    def check():
        try:
            check_and_update_accuracy()
            flash("到期结果已更新。", "success")
        except Exception as exc:
            flash(format_user_error(exc), "error")
        return redirect(url_for("dashboard"))

    @app.post("/execute-paper")
    def execute_paper():
        prediction_id_value = request.form.get("prediction_id", "").strip()
        prediction_id = int(prediction_id_value) if prediction_id_value else None
        try:
            execute_prediction_order(prediction_id=prediction_id, mode="paper")
            flash("纸面订单已记录。", "success")
        except Exception as exc:
            flash(format_user_error(exc), "error")
        return redirect(url_for("dashboard"))

    @app.post("/execute-live")
    def execute_live():
        if not ENABLE_LIVE_TRADING:
            flash("真实交易未启用（ENABLE_LIVE_TRADING=false）。", "error")
            return redirect(url_for("dashboard"))

        prediction_id_value = request.form.get("prediction_id", "").strip()
        confirm_text = request.form.get("confirm", "").strip()
        
        if confirm_text != LIVE_CONFIRM_TEXT:
            flash(f"确认文本不匹配，请输入确认信息以执行实盘交易。", "error")
            return redirect(url_for("dashboard"))

        prediction_id = int(prediction_id_value) if prediction_id_value else None
        try:
            result = execute_prediction_order(prediction_id=prediction_id, mode="live", confirm=confirm_text)
            flash(f"真实订单已执行（Trade Order ID: {result['trade_order_id']}）。", "success")
        except Exception as exc:
            flash(format_user_error(exc), "error")
        return redirect(url_for("dashboard"))

    @app.get("/api/chart-data")
    def chart_data():
        symbol = request.args.get("symbol", "").strip() or None
        limit = int(request.args.get("limit", "100"))
        try:
            start_utc = normalize_chart_utc_param(request.args.get("start_utc"))
            end_utc = normalize_chart_utc_param(request.args.get("end_utc"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        rows = list_chart_predictions(symbol=symbol, limit=limit, start_utc=start_utc, end_utc=end_utc)
        return jsonify(
            {
                "symbol": symbol,
                "points": [
                    {
                        "time_utc": row["prediction_time"],
                        "symbol": row["symbol"],
                        "entry_price": row["entry_price"] or row["current_price"],
                        "target_price": row["target_price"],
                        "actual_result_price": row["actual_result_price"],
                        "expected_profit": row["expected_profit"] or 0,
                        "expected_loss": row["expected_loss"] or 0,
                        "direction": row["prediction_direction"],
                        "position_side": row["position_side"],
                        "confidence": row["confidence"],
                    }
                    for row in rows
                ],
            }
        )

    return app


def normalize_chart_utc_param(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return to_iso(from_iso(value))
    except ValueError as exc:
        raise ValueError(f"Invalid UTC datetime: {value}") from exc


def parse_positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def build_pagination(page_param: str, page_size: int, total_items: int) -> dict[str, int | bool | str]:
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = min(parse_positive_int(request.args.get(page_param), 1), total_pages)
    return {
        "page_param": page_param,
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "offset": (page - 1) * page_size,
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "previous_page": max(1, page - 1),
        "next_page": min(total_pages, page + 1),
    }


def page_url(page_param: str, page: int) -> str:
    args = request.args.to_dict(flat=True)
    if page <= 1:
        args.pop(page_param, None)
    else:
        args[page_param] = str(page)
    query = urlencode({key: value for key, value in args.items() if value})
    return f"/?{query}" if query else "/"


def maybe_start_auto_worker(app: Flask, manager: AutoTaskManager) -> None:
    """按配置启用后台自动任务。"""

    if not AUTO_RUN_ENABLED:
        return

    run_main_flag = os.getenv("WERKZEUG_RUN_MAIN")
    if run_main_flag not in {None, "true"}:
        return

    config = build_default_auto_config()
    result = manager.start(config)
    if result.get("started"):
        app.logger.info("Auto runner started in background thread")


def format_user_error(exc: Exception) -> str:
    """把底层异常转换成页面可读的错误提示。"""

    message = str(exc)
    if "api.binance.com" in message or "RequestTimeout" in message or "timed out" in message:
        return (
            "创建预测失败：连接 Binance 行情接口超时。"
            "这通常不是 OpenAI 参数问题，而是当前网络访问 api.binance.com 不通或太慢。"
            "可以稍后重试，或在 config.yaml 的 exchange 段配置代理。"
        )
    if "OPENAI_API_KEY" in message:
        return "创建预测失败：缺少 OpenAI API Key，请检查 config.yaml 的 providers.openai.api_key。"
    if "OpenAI" in message:
        return f"创建预测失败：OpenAI 或中转站调用异常：{message}"
    return f"操作失败：{message}"


app = create_app()
