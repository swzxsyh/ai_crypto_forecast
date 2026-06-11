"""命令行界面。"""

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
from crypto_predictor.database import get_overall_accuracy
from crypto_predictor.repositories import get_repository
from crypto_predictor.service import run_prediction_once, run_predictions_for_symbols
from crypto_predictor.validator import check_and_update_accuracy


def build_arg_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""

    parser = argparse.ArgumentParser(description="虚拟币模拟预测系统（只记录，不下单）")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="初始化 SQLite 数据库")
    subparsers.add_parser("list-symbols", help="查看配置中的候选交易对")

    web_parser = subparsers.add_parser("web", help="启动本地 Web 看板")
    web_parser.add_argument("--host", default=WEB_HOST, help="监听地址")
    web_parser.add_argument("--port", type=int, default=WEB_PORT, help="监听端口")
    web_parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=WEB_DEBUG,
        help="是否开启 Flask debug 模式",
    )

    account_parser = subparsers.add_parser("account", help="只读检查 Binance 账户连接")
    account_parser.add_argument("--raw", action="store_true", help="输出完整账户快照")

    execute_parser = subparsers.add_parser("execute-order", help="执行最新或指定预测的模拟/真实订单")
    execute_parser.add_argument("--prediction-id", type=int, help="指定预测记录 ID；不传则执行最新预测")
    execute_parser.add_argument("--mode", choices=["paper", "live"], default="paper", help="paper 默认模拟，live 真实下单")
    execute_parser.add_argument("--confirm", help="真实下单确认文本，必须匹配 LIVE_CONFIRM_TEXT")

    predict_parser = subparsers.add_parser("predict", help="获取行情、调用 AI、写入预测")
    predict_parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="单个交易对，例如 BTC/USDT")
    predict_parser.add_argument(
        "--symbols",
        nargs="+",
        help="批量指定多个交易对，例如 --symbols BTC/USDT ETH/USDT SOL/USDT",
    )
    predict_parser.add_argument(
        "--all-symbols",
        action="store_true",
        help="预测 config.yaml 中 crypto.symbols 配置的所有交易对",
    )
    predict_parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME, help="K 线周期，例如 1h")
    predict_parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="K 线数量，默认 24")
    predict_parser.add_argument(
        "--model-type",
        choices=["openai", "anthropic"],
        default="openai",
        help="AI 模型提供商",
    )

    check_parser = subparsers.add_parser("check", help="检查已到期预测并更新准确性")
    check_parser.add_argument(
        "--sideways-threshold-pct",
        type=float,
        default=DEFAULT_SIDEWAYS_THRESHOLD_PCT,
        help="SIDEWAYS 判断阈值，默认 0.002 即 0.2%",
    )

    subparsers.add_parser("stats", help="查看所有已验证预测的总体准确率")

    auto_parser = subparsers.add_parser("auto-run", help="定时自动执行：预测 + 可选纸面模拟 + 到期校验")
    auto_parser.add_argument(
        "--interval-seconds",
        type=int,
        default=AUTO_RUN_INTERVAL_SECONDS,
        help="执行间隔秒数，默认读取 automation.interval_seconds",
    )
    auto_parser.add_argument("--cycles", type=int, default=0, help="执行轮次，0 表示无限循环直到 Ctrl+C")
    auto_parser.add_argument(
        "--symbols",
        nargs="+",
        help="指定自动任务交易对，例如 --symbols BTC/USDT ETH/USDT",
    )
    auto_parser.add_argument(
        "--all-symbols",
        action="store_true",
        help="自动任务使用 config.yaml 的全部交易对",
    )
    auto_parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME, help="K 线周期，例如 1h")
    auto_parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="K 线数量，默认 24")
    auto_parser.add_argument(
        "--model-type",
        choices=["openai", "anthropic"],
        default=AUTO_RUN_MODEL_TYPE,
        help="AI 模型提供商",
    )
    auto_parser.add_argument(
        "--execute-paper",
        action=argparse.BooleanOptionalAction,
        default=AUTO_RUN_EXECUTE_PAPER,
        help="是否每次预测后自动执行纸面模拟",
    )
    auto_parser.add_argument(
        "--check-accuracy",
        action=argparse.BooleanOptionalAction,
        default=AUTO_RUN_CHECK_ACCURACY,
        help="是否每轮结束后自动执行到期校验",
    )

    return parser


def main() -> None:
    """命令行入口。"""

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

        result = execute_prediction_order(
            prediction_id=args.prediction_id,
            mode=args.mode,
            confirm=args.confirm,
        )
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
        result = get_overall_accuracy()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "auto-run":
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

    parser.error(f"未知命令: {args.command}")
