"""交易所客户端工厂。"""

from __future__ import annotations

import logging
import socket
import threading
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

logger = logging.getLogger(__name__)
_EXCHANGE_CACHE_LOCK = threading.RLock()
_EXCHANGE_CACHE: dict[str, Any] = {}
_WARMUP_THREADS: dict[str, threading.Thread] = {}


def build_exchange(exchange_id: str = DEFAULT_EXCHANGE_ID) -> Any:
    """创建并缓存 ccxt 交易所实例。

    公开行情只需要一个复用的 exchange 实例。实例一旦 load_markets 成功，
    后续 fetch_ohlcv 会复用内存里的 markets，避免每个定时周期重复请求 exchangeInfo。
    """

    with _EXCHANGE_CACHE_LOCK:
        cached = _EXCHANGE_CACHE.get(exchange_id)
        if cached is not None:
            return cached

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

    exchange = exchange_class(config)
    with _EXCHANGE_CACHE_LOCK:
        cached = _EXCHANGE_CACHE.get(exchange_id)
        if cached is not None:
            return cached
        _EXCHANGE_CACHE[exchange_id] = exchange
        return exchange


def warm_exchange_market_cache(exchange_id: str = DEFAULT_EXCHANGE_ID) -> bool:
    """启动时预热交易对元数据，并保存在内存里的 ccxt 实例上。"""

    exchange = build_exchange(exchange_id)
    if getattr(exchange, "markets", None):
        return True

    try:
        exchange.load_markets()
        logger.info("Exchange market cache warmed", extra={"exchange_id": exchange_id})
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Exchange market cache warmup failed: %s", exc, extra={"exchange_id": exchange_id})
        return False




def warm_exchange_market_cache_async(exchange_id: str = DEFAULT_EXCHANGE_ID) -> bool:
    """Warm exchange markets in a background thread without blocking app startup."""

    with _EXCHANGE_CACHE_LOCK:
        exchange = _EXCHANGE_CACHE.get(exchange_id)
        if exchange is not None and getattr(exchange, "markets", None):
            return False

        existing_thread = _WARMUP_THREADS.get(exchange_id)
        if existing_thread is not None and existing_thread.is_alive():
            return False

        thread = threading.Thread(
            target=_warm_exchange_market_cache_thread,
            args=(exchange_id,),
            name=f"exchange-market-warmup-{exchange_id}",
            daemon=True,
        )
        _WARMUP_THREADS[exchange_id] = thread
        thread.start()
        logger.info("Exchange market cache warmup scheduled", extra={"exchange_id": exchange_id})
        return True


def _warm_exchange_market_cache_thread(exchange_id: str) -> None:
    try:
        warm_exchange_market_cache(exchange_id)
    finally:
        with _EXCHANGE_CACHE_LOCK:
            thread = _WARMUP_THREADS.get(exchange_id)
            if thread is threading.current_thread():
                _WARMUP_THREADS.pop(exchange_id, None)

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


