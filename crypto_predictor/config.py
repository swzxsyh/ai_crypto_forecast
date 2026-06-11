"""全局配置。

所有默认值都允许通过环境变量覆盖，方便后续部署到定时任务、服务器或容器。
"""

from __future__ import annotations

import os

from crypto_predictor.config_loader import load_yaml_env


LOADED_CONFIG_PATH = load_yaml_env()


def parse_csv(value: str | None, fallback: tuple[str, ...]) -> tuple[str, ...]:
    """解析逗号分隔配置。"""

    if not value:
        return fallback

    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or fallback


def parse_bool(value: str | None, fallback: bool) -> bool:
    """解析布尔配置。"""

    if value is None:
        return fallback
    return value.lower() in {"1", "true", "yes", "on"}


def parse_int(value: str | None, fallback: int) -> int:
    """解析整型配置，异常时回退。"""

    if value is None:
        return fallback
    try:
        return int(value)
    except ValueError:
        return fallback


DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").strip().lower() or "sqlite"
DB_PATH = os.getenv("PREDICTION_DB_PATH", "crypto_predictions.sqlite3")
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "")
EXCHANGE_TIMEOUT_MS = int(os.getenv("EXCHANGE_TIMEOUT_MS", "30000"))
EXCHANGE_PROXY = os.getenv("EXCHANGE_PROXY", "")
EXCHANGE_HTTP_PROXY = os.getenv("EXCHANGE_HTTP_PROXY", "")
EXCHANGE_HTTPS_PROXY = os.getenv("EXCHANGE_HTTPS_PROXY", "")
EXCHANGE_AUTO_PROXY = parse_bool(os.getenv("EXCHANGE_AUTO_PROXY", "true"), fallback=True)
EXCHANGE_AUTO_PROXY_PORTS = parse_csv(
    os.getenv("EXCHANGE_AUTO_PROXY_PORTS"),
    fallback=("7890", "7897", "7899", "10809", "1080"),
)
DEFAULT_SYMBOLS = parse_csv(os.getenv("CRYPTO_SYMBOLS"), fallback=(os.getenv("CRYPTO_SYMBOL", "BTC/USDT"),))
DEFAULT_SYMBOL = os.getenv("CRYPTO_SYMBOL", DEFAULT_SYMBOLS[0])
DEFAULT_TIMEFRAME = os.getenv("CRYPTO_TIMEFRAME", "1h")
DEFAULT_TIMEFRAMES = parse_csv(
    os.getenv("CRYPTO_TIMEFRAMES"),
    fallback=("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"),
)
DEFAULT_LIMIT = int(os.getenv("CRYPTO_KLINE_LIMIT", "24"))
DEFAULT_EXCHANGE_ID = os.getenv("CRYPTO_EXCHANGE_ID", "binance")
MARKET_DATA_CACHE_TTL_SECONDS = max(0, parse_int(os.getenv("MARKET_DATA_CACHE_TTL_SECONDS"), 0))
MARKET_DATA_RETRY_ATTEMPTS = max(1, parse_int(os.getenv("MARKET_DATA_RETRY_ATTEMPTS"), 3))
MARKET_DATA_RETRY_INITIAL_DELAY_SECONDS = float(os.getenv("MARKET_DATA_RETRY_INITIAL_DELAY_SECONDS", "0.5"))

CONTRACT_DEFAULT_MARGIN = float(os.getenv("CONTRACT_DEFAULT_MARGIN", "100"))
CONTRACT_MIN_MARGIN = float(os.getenv("CONTRACT_MIN_MARGIN", "0"))
CONTRACT_MAX_MARGIN = float(os.getenv("CONTRACT_MAX_MARGIN", "500"))
CONTRACT_DEFAULT_LEVERAGE = int(os.getenv("CONTRACT_DEFAULT_LEVERAGE", "3"))
CONTRACT_MAX_LEVERAGE = int(os.getenv("CONTRACT_MAX_LEVERAGE", "10"))

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")
BINANCE_SANDBOX = parse_bool(os.getenv("BINANCE_SANDBOX", "true"), fallback=True)
BINANCE_MARKET_TYPE = os.getenv("BINANCE_MARKET_TYPE", "future")

TRADING_MODE = os.getenv("TRADING_MODE", "paper")
ENABLE_LIVE_TRADING = parse_bool(os.getenv("ENABLE_LIVE_TRADING", "false"), fallback=False)
LIVE_CONFIRM_TEXT = os.getenv("LIVE_CONFIRM_TEXT", "I_UNDERSTAND_LIVE_TRADING")
PLACE_BRACKET_ORDERS = parse_bool(os.getenv("PLACE_BRACKET_ORDERS", "false"), fallback=False)
POSITION_SIDE_MODE = os.getenv("POSITION_SIDE_MODE", "one_way")

RISK_MAX_MARGIN_PER_TRADE = float(os.getenv("RISK_MAX_MARGIN_PER_TRADE", str(CONTRACT_MAX_MARGIN)))
RISK_MAX_LEVERAGE = int(os.getenv("RISK_MAX_LEVERAGE", str(CONTRACT_MAX_LEVERAGE)))
RISK_ALLOWED_SYMBOLS = parse_csv(os.getenv("RISK_ALLOWED_SYMBOLS"), fallback=DEFAULT_SYMBOLS)

# 用户指定第一版接入 gpt-5.5；保留环境变量，方便以后灰度或切换模型。
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
DEFAULT_OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")

# SIDEWAYS 判断阈值。0.002 表示 0.2%。
DEFAULT_SIDEWAYS_THRESHOLD_PCT = float(os.getenv("SIDEWAYS_THRESHOLD_PCT", "0.002"))

FEAR_GREED_ENABLED = parse_bool(os.getenv("FEAR_GREED_ENABLED", "true"), fallback=True)
FEAR_GREED_API_URL = os.getenv("FEAR_GREED_API_URL", "https://api.alternative.me/fng/?limit=1&format=json")
FEAR_GREED_TIMEOUT_SECONDS = max(1, parse_int(os.getenv("FEAR_GREED_TIMEOUT_SECONDS"), 5))

WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "local-simulation-dashboard")
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = max(1, parse_int(os.getenv("WEB_PORT"), 8000))
WEB_DEBUG = parse_bool(os.getenv("WEB_DEBUG", "false"), fallback=False)
WEB_AUTO_REFRESH_SECONDS = max(0, parse_int(os.getenv("WEB_AUTO_REFRESH_SECONDS"), 20))
WEB_DEFAULT_TIMEZONE = os.getenv("WEB_DEFAULT_TIMEZONE", "Asia/Shanghai")
WEB_TIMEZONE_OPTIONS = parse_csv(
    os.getenv("WEB_TIMEZONE_OPTIONS"),
    fallback=("UTC", "Asia/Shanghai", "Asia/Tokyo", "Europe/London", "America/New_York"),
)

AUTO_RUN_ENABLED = parse_bool(os.getenv("AUTO_RUN_ENABLED", "false"), fallback=False)
AUTO_RUN_INTERVAL_SECONDS = max(10, parse_int(os.getenv("AUTO_RUN_INTERVAL_SECONDS"), 3600))
AUTO_RUN_PREDICT_ALL_SYMBOLS = parse_bool(os.getenv("AUTO_RUN_PREDICT_ALL_SYMBOLS", "true"), fallback=True)
AUTO_RUN_EXECUTE_PAPER = parse_bool(os.getenv("AUTO_RUN_EXECUTE_PAPER", "true"), fallback=True)
AUTO_RUN_EXECUTE_LIVE = parse_bool(os.getenv("AUTO_RUN_EXECUTE_LIVE", "false"), fallback=False)
AUTO_RUN_CHECK_ACCURACY = parse_bool(os.getenv("AUTO_RUN_CHECK_ACCURACY", "true"), fallback=True)
AUTO_RUN_MODEL_TYPE = os.getenv("AUTO_RUN_MODEL_TYPE", "openai")

LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_RETENTION_DAYS = max(1, parse_int(os.getenv("LOG_RETENTION_DAYS"), 30))
