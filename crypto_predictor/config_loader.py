"""YAML 配置加载器。

优先级：
1. 系统环境变量优先，适合服务器、CI、容器部署。
2. YAML 文件作为本地开发配置，适合保存 API Key、模型、交易对列表等变量。

默认读取当前工作目录下的 config.yaml 或 config.yml；也可以通过
CRYPTO_CONFIG_PATH 指定其它路径。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_FILES = ("config.yaml", "config.yml")


def load_yaml_env(config_path: str | None = None) -> str | None:
    """读取 YAML 配置，并写入尚未存在的环境变量。

    返回实际加载的配置文件路径；如果没有找到配置文件，返回 None。
    """

    path = resolve_config_path(config_path)
    if path is None:
        return None

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("检测到 YAML 配置文件，但缺少 PyYAML，请先执行：pip install PyYAML") from exc

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"YAML 配置文件必须是对象结构：{path}")

    for key, value in extract_env_values(data).items():
        if value is not None and key not in os.environ:
            os.environ[key] = encode_env_value(value)

    return str(path)


def resolve_config_path(config_path: str | None = None) -> Path | None:
    """解析配置文件路径。"""

    explicit_path = config_path or os.getenv("CRYPTO_CONFIG_PATH")
    if explicit_path:
        path = Path(explicit_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"指定的配置文件不存在：{path}")
        return path

    for file_name in DEFAULT_CONFIG_FILES:
        path = Path.cwd() / file_name
        if path.exists():
            return path

    return None


def extract_env_values(data: dict[str, Any]) -> dict[str, Any]:
    """把友好的 YAML 分组结构映射到系统环境变量名。"""

    env_values: dict[str, Any] = {}

    # 允许直接写 env: {OPENAI_API_KEY: "..."}，方便高级用户完整控制。
    direct_env = data.get("env", {})
    if direct_env:
        if not isinstance(direct_env, dict):
            raise ValueError("config.yaml 中的 env 必须是对象")
        env_values.update(direct_env)

    providers_config = read_section(data, "providers")
    openai_config = read_provider_section(data, providers_config, "openai")
    anthropic_config = read_provider_section(data, providers_config, "anthropic")
    database_config = read_section(data, "database")
    exchange_config = read_section(data, "exchange")
    crypto_config = read_section(data, "crypto")
    contract_config = read_section(data, "contract")
    binance_config = read_section(data, "binance")
    trading_config = read_section(data, "trading")
    risk_config = read_section(data, "risk")
    validation_config = read_section(data, "validation")
    sentiment_config = read_section(data, "sentiment")
    web_config = read_section(data, "web")
    automation_config = read_section(data, "automation")
    log_config = read_section(data, "log")

    env_values.update(
        {
            "OPENAI_API_KEY": openai_config.get("api_key"),
            "OPENAI_MODEL": openai_config.get("model"),
            "OPENAI_BASE_URL": openai_config.get("base_url"),
            "ANTHROPIC_API_KEY": anthropic_config.get("api_key"),
            "ANTHROPIC_MODEL": anthropic_config.get("model"),
            "ANTHROPIC_BASE_URL": anthropic_config.get("base_url"),
            "PREDICTION_DB_PATH": database_config.get("path"),
            "DB_BACKEND": database_config.get("backend"),
            "POSTGRES_DSN": database_config.get("postgres_dsn"),
            "MYSQL_DSN": database_config.get("mysql_dsn"),
            "EXCHANGE_TIMEOUT_MS": exchange_config.get("timeout_ms"),
            "EXCHANGE_PROXY": exchange_config.get("proxy"),
            "EXCHANGE_HTTP_PROXY": exchange_config.get("http_proxy"),
            "EXCHANGE_HTTPS_PROXY": exchange_config.get("https_proxy"),
            "EXCHANGE_AUTO_PROXY": exchange_config.get("auto_proxy"),
            "EXCHANGE_AUTO_PROXY_PORTS": exchange_config.get("auto_proxy_ports"),
            "CRYPTO_SYMBOL": crypto_config.get("symbol"),
            "CRYPTO_SYMBOLS": crypto_config.get("symbols"),
            "CRYPTO_TIMEFRAME": crypto_config.get("timeframe"),
            "CRYPTO_TIMEFRAMES": crypto_config.get("timeframes"),
            "CRYPTO_KLINE_LIMIT": crypto_config.get("kline_limit"),
            "CRYPTO_EXCHANGE_ID": crypto_config.get("exchange_id"),
            "MARKET_DATA_CACHE_TTL_SECONDS": crypto_config.get("market_data_cache_ttl_seconds"),
            "MARKET_DATA_RETRY_ATTEMPTS": crypto_config.get("market_data_retry_attempts"),
            "MARKET_DATA_RETRY_INITIAL_DELAY_SECONDS": crypto_config.get("market_data_retry_initial_delay_seconds"),
            "CONTRACT_DEFAULT_MARGIN": contract_config.get("default_margin"),
            "CONTRACT_MIN_MARGIN": contract_config.get("min_margin"),
            "CONTRACT_MAX_MARGIN": contract_config.get("max_margin"),
            "CONTRACT_DEFAULT_LEVERAGE": contract_config.get("default_leverage"),
            "CONTRACT_MAX_LEVERAGE": contract_config.get("max_leverage"),
            "BINANCE_API_KEY": binance_config.get("api_key"),
            "BINANCE_SECRET": binance_config.get("secret"),
            "BINANCE_SANDBOX": binance_config.get("sandbox"),
            "BINANCE_MARKET_TYPE": binance_config.get("market_type"),
            "TRADING_MODE": trading_config.get("mode"),
            "ENABLE_LIVE_TRADING": trading_config.get("enable_live_trading"),
            "LIVE_CONFIRM_TEXT": trading_config.get("live_confirm_text"),
            "PLACE_BRACKET_ORDERS": trading_config.get("place_bracket_orders"),
            "POSITION_SIDE_MODE": trading_config.get("position_side_mode"),
            "RISK_MAX_MARGIN_PER_TRADE": risk_config.get("max_margin_per_trade"),
            "RISK_MAX_LEVERAGE": risk_config.get("max_leverage"),
            "RISK_ALLOWED_SYMBOLS": risk_config.get("allowed_symbols"),
            "SIDEWAYS_THRESHOLD_PCT": validation_config.get("sideways_threshold_pct"),
            "FEAR_GREED_ENABLED": sentiment_config.get("fear_greed_enabled"),
            "FEAR_GREED_API_URL": sentiment_config.get("fear_greed_api_url"),
            "FEAR_GREED_TIMEOUT_SECONDS": sentiment_config.get("fear_greed_timeout_seconds"),
            "WEB_SECRET_KEY": web_config.get("secret_key"),
            "WEB_HOST": web_config.get("host"),
            "WEB_PORT": web_config.get("port"),
            "WEB_DEBUG": web_config.get("debug"),
            "WEB_AUTO_REFRESH_SECONDS": web_config.get("auto_refresh_seconds"),
            "WEB_DEFAULT_TIMEZONE": web_config.get("default_timezone"),
            "WEB_TIMEZONE_OPTIONS": web_config.get("timezones"),
            "AUTO_RUN_ENABLED": automation_config.get("enabled"),
            "AUTO_RUN_INTERVAL_SECONDS": automation_config.get("interval_seconds"),
            "AUTO_RUN_PREDICT_ALL_SYMBOLS": automation_config.get("predict_all_symbols"),
            "AUTO_RUN_EXECUTE_PAPER": automation_config.get("execute_paper"),
            "AUTO_RUN_CHECK_ACCURACY": automation_config.get("check_accuracy"),
            "AUTO_RUN_MODEL_TYPE": automation_config.get("model_type"),
            "LOG_DIR": log_config.get("dir"),
            "LOG_LEVEL": log_config.get("level"),
            "LOG_RETENTION_DAYS": log_config.get("retention_days"),
        }
    )

    return env_values


def encode_env_value(value: Any) -> str:
    """将 YAML 值转换成环境变量字符串。"""

    if isinstance(value, list):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    return str(value)


def read_section(data: dict[str, Any], section_name: str) -> dict[str, Any]:
    """安全读取 YAML 中的对象分组。"""

    section = data.get(section_name, {})
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ValueError(f"config.yaml 中的 {section_name} 必须是对象")
    return section


def read_provider_section(
    data: dict[str, Any],
    providers_config: dict[str, Any],
    provider_name: str,
) -> dict[str, Any]:
    """读取 provider 配置，并兼容旧的顶层 openai 写法。"""

    legacy_section = read_section(data, provider_name)
    provider_section = providers_config.get(provider_name, {})

    if provider_section is None:
        provider_section = {}
    if not isinstance(provider_section, dict):
        raise ValueError(f"config.yaml 中的 providers.{provider_name} 必须是对象")

    return {**legacy_section, **provider_section}
