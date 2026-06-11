"""Binance 账户只读接入。"""

from __future__ import annotations

from typing import Any

from crypto_predictor.config import BINANCE_API_KEY, BINANCE_MARKET_TYPE, BINANCE_SANDBOX, BINANCE_SECRET


def get_binance_account_snapshot() -> dict[str, Any]:
    """读取 Binance 账户余额与持仓快照。"""

    if not BINANCE_API_KEY or not BINANCE_SECRET:
        raise RuntimeError("缺少 BINANCE_API_KEY 或 BINANCE_SECRET")

    try:
        import ccxt
    except ImportError as exc:
        raise RuntimeError("缺少 ccxt SDK，请先执行：pip install ccxt") from exc

    exchange = ccxt.binance(
        {
            "apiKey": BINANCE_API_KEY,
            "secret": BINANCE_SECRET,
            "enableRateLimit": True,
            "options": {
                "defaultType": BINANCE_MARKET_TYPE,
            },
        }
    )

    if BINANCE_SANDBOX:
        exchange.set_sandbox_mode(True)

    balance = exchange.fetch_balance()
    positions = []
    if hasattr(exchange, "fetch_positions"):
        try:
            positions = exchange.fetch_positions()
        except Exception:
            positions = []

    return {
        "exchange": "binance",
        "sandbox": BINANCE_SANDBOX,
        "market_type": BINANCE_MARKET_TYPE,
        "balance_total": balance.get("total", {}),
        "balance_free": balance.get("free", {}),
        "positions": positions,
    }
