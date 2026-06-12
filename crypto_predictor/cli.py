"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys

from crypto_predictor.auto_runner import resolve_auto_symbols, run_auto_loop
from crypto_predictor.config import (
    AUTO_RUN_CHECK_ACCURACY,
    AUTO_RUN_EXECUTE_PAPER,
    AUTO_RUN_INTERVAL_SECONDS,
    AUTO_RUN_MODEL_TYPE,
    LOG_DIR,
    LOG_LEVEL,
    LOG_RETENTION_DAYS,
    WEB_DEBUG,
    WEB_HOST,
    WEB_PORT,
)
from crypto_predictor.config import DB_PATH, DEFAULT_LIMIT, DEFAULT_SIDEWAYS_THRESHOLD_PCT
from crypto_predictor.config import DEFAULT_SYMBOL, DEFAULT_SYMBOLS, DEFAULT_TIMEFRAME
from crypto_predictor.exchange import warm_exchange_market_cache
from crypto_predictor.infrastructure.persistence.repository_factory import get_repository
from crypto_predictor.service import run_prediction_once, run_predictions_for_symbols
from crypto_predictor.validator import check_and_update_accuracy


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command-line argument parser."""

    parser = argparse.ArgumentParser(description="AI crypto simulation predictor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize database schema")
    subparsers.add_parser("list-symbols", help="List configured symbols")

    web_parser = subparsers.add_parser("web", help="Start local Flask dashboard")
    web_parser.add_argument("--host", default=WEB_HOST, help="Host to bind")
    web_parser.add_argument("--port", type=int, default=WEB_PORT, help="Port to bind")
    web_parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=WEB_DEBUG,
        help="Enable Flask debug mode",
    )

    account_parser = subparsers.add_parser("account", help="Check Binance account connection")
    account_parser.add_argument("--raw", action="store_true", help="Print raw account snapshot")

    execute_parser = subparsers.add_parser("execute-order", help="Execute latest or selected prediction order")
    execute_parser.add_argument("--prediction-id", type=int, help="Prediction record ID; latest if omitted")
    execute_parser.add_argument("--mode", choices=["paper", "live"], default="paper", help="Execution mode")
    execute_parser.add_argument("--confirm", help="Required confirmation text for live execution")

    predict_parser = subparsers.add_parser("predict", help="Fetch market data, call AI, and save prediction")
    predict_parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Single symbol, e.g. BTC/USDT")
    predict_parser.add_argument("--symbols", nargs="+", help="Multiple symbols")
    predict_parser.add_argument("--all-symbols", action="store_true", help="Predict all configured symbols")
    predict_parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME, help="Kline timeframe, e.g. 1h")
    predict_parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Kline limit")
    predict_parser.add_argument(
        "--model-type",
        choices=["openai", "anthropic"],
        default="openai",
        help="AI provider",
    )

    check_parser = subparsers.add_parser("check", help="Check expired predictions and update accuracy")
    check_parser.add_argument(
        "--sideways-threshold-pct",
        type=float,
        default=DEFAULT_SIDEWAYS_THRESHOLD_PCT,
        help="SIDEWAYS threshold ratio, default 0.002",
    )

    subparsers.add_parser("stats", help="Show overall checked prediction accuracy")

    auto_parser = subparsers.add_parser("auto-run", help="Run scheduled prediction loop")
    auto_parser.add_argument(
        "--interval-seconds",
        type=int,
        default=AUTO_RUN_INTERVAL_SECONDS,
        help="Execution interval in seconds",
    )
    auto_parser.add_argument("--cycles", type=int, default=0, help="Cycle count; 0 means forever")
    auto_parser.add_argument("--symbols", nargs="+", help="Symbols for auto task")
    auto_parser.add_argument("--all-symbols", action="store_true", help="Use all configured symbols")
    auto_parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME, help="Kline timeframe")
    auto_parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Kline limit")
    auto_parser.add_argument(
        "--model-type",
        choices=["openai", "anthropic"],
        default=AUTO_RUN_MODEL_TYPE,
        help="AI provider",
    )
    auto_parser.add_argument(
        "--execute-paper",
        action=argparse.BooleanOptionalAction,
        default=AUTO_RUN_EXECUTE_PAPER,
        help="Execute paper order after prediction",
    )
    auto_parser.add_argument(
        "--check-accuracy",
        action=argparse.BooleanOptionalAction,
        default=AUTO_RUN_CHECK_ACCURACY,
        help="Check expired prediction accuracy after each cycle",
    )

    return parser


def main() -> None:
    """CLI entrypoint."""

    from crypto_predictor.logging_setup import setup_logging

    setup_logging(log_dir=LOG_DIR, level=LOG_LEVEL, retention_days=LOG_RETENTION_DAYS)

    parser = build_arg_parser()
    if len(sys.argv) == 1:
        args = parser.parse_args(["web"])
    else:
        args = parser.parse_args()

    if args.command == "init-db":
        get_repository().init_schema()
        print(json.dumps({"status": "ok", "db_path": DB_PATH}, ensure_ascii=False, indent=2))
        return

    if args.command == "list-symbols":
        print(json.dumps({"default_symbol": DEFAULT_SYMBOL, "symbols": list(DEFAULT_SYMBOLS)}, ensure_ascii=False, indent=2))
        return

    if args.command == "web":
        from crypto_predictor.web_app import create_app

        app = create_app()
        app.run(host=args.host, port=args.port, debug=args.debug)
        return

    if args.command == "account":
        from crypto_predictor.broker.account import get_binance_account_snapshot

        snapshot = get_binance_account_snapshot()
        if args.raw:
            print(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))
        else:
            print(
                json.dumps(
                    {
                        "exchange": snapshot["exchange"],
                        "sandbox": snapshot["sandbox"],
                        "market_type": snapshot["market_type"],
                        "balance_total": snapshot["balance_total"],
                        "positions_count": len(snapshot["positions"]),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
        return

    if args.command == "execute-order":
        from crypto_predictor.broker.executor import execute_prediction_order

        result = execute_prediction_order(prediction_id=args.prediction_id, mode=args.mode, confirm=args.confirm)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return

    if args.command == "predict":
        if args.all_symbols:
            symbols = DEFAULT_SYMBOLS
        elif args.symbols:
            symbols = tuple(args.symbols)
        else:
            symbols = None

        if symbols:
            result = {
                "count": len(symbols),
                "results": run_predictions_for_symbols(
                    symbols=symbols,
                    timeframe=args.timeframe,
                    limit=args.limit,
                    model_type=args.model_type,
                ),
            }
        else:
            result = run_prediction_once(
                symbol=args.symbol,
                timeframe=args.timeframe,
                limit=args.limit,
                model_type=args.model_type,
            )

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "check":
        result = check_and_update_accuracy(sideways_threshold_pct=args.sideways_threshold_pct)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "stats":
        result = get_repository().get_overall_accuracy()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "auto-run":
        warm_exchange_market_cache()
        symbols = resolve_auto_symbols(all_symbols=args.all_symbols, symbols=args.symbols)
        result = run_auto_loop(
            interval_seconds=max(10, args.interval_seconds),
            cycles=max(0, args.cycles),
            symbols=symbols,
            timeframe=args.timeframe,
            limit=args.limit,
            model_type=args.model_type,
            execute_paper=args.execute_paper,
            check_accuracy=args.check_accuracy,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    parser.error(f"Unknown command: {args.command}")
