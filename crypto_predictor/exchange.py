"""交易所客户端工厂。"""

from __future__ import annotations

import socket
from typing import Any

from crypto_predictor.config import (
    DEFAULT_EXCHANGE_ID,
    EXCHANGE_AUTO_PROXY,
    EXCHANGE_AUTO_PROXY_PORTS,
    EXCHANGE_HTTP_PROXY,
    EXCHANGE_HTTPS_PROXY,
    EXCHANGE_PROXY,
    EXCHANGE_TIMEOUT_MS,
)


def build_exchange(exchange_id: str = DEFAULT_EXCHANGE_ID) -> Any:
    """创建 ccxt 交易所实例。

    这里只读取公开行情，不配置交易 API Key。代理和超时可通过 YAML/环境变量配置。
    """

    try:
        import ccxt
    except ImportError as exc:
        raise RuntimeError("缺少 ccxt SDK，请先执行：pip install ccxt") from exc

    exchange_class = getattr(ccxt, exchange_id)
    config: dict[str, Any] = {
        "enableRateLimit": True,
        "timeout": EXCHANGE_TIMEOUT_MS,
        "options": {
            # Binance 现货市场；真实合约交易在 broker 层单独配置 future。
            "defaultType": "spot",
        },
    }

    proxies = build_proxy_config()
    if proxies:
        config["proxies"] = proxies

    if EXCHANGE_PROXY:
        # ccxt 也支持统一 proxy 字段，保留给部分网络环境使用。
        config["proxy"] = EXCHANGE_PROXY

    return exchange_class(config)


def build_proxy_config() -> dict[str, str]:
    """构建 requests 使用的代理配置。"""

    proxies: dict[str, str] = {}
    if EXCHANGE_HTTP_PROXY:
        proxies["http"] = EXCHANGE_HTTP_PROXY
    if EXCHANGE_HTTPS_PROXY:
        proxies["https"] = EXCHANGE_HTTPS_PROXY
    if not proxies and EXCHANGE_AUTO_PROXY:
        detected_proxy = detect_local_proxy()
        if detected_proxy:
            proxies["http"] = detected_proxy
            proxies["https"] = detected_proxy
    return proxies


def detect_local_proxy() -> str | None:
    """自动探测本机常见 Clash HTTP/Mixed 代理端口。"""

    for port_text in EXCHANGE_AUTO_PROXY_PORTS:
        try:
            port = int(port_text)
        except ValueError:
            continue

        if is_local_port_open(port):
            return f"http://127.0.0.1:{port}"

    return None


def is_local_port_open(port: int) -> bool:
    """检查本机端口是否可连接。"""

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False
