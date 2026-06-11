"""行情数据获取与 Prompt 数据压缩。"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from crypto_predictor.config import (
    DEFAULT_EXCHANGE_ID,
    DEFAULT_LIMIT,
    DEFAULT_SYMBOL,
    DEFAULT_TIMEFRAME,
    MARKET_DATA_CACHE_TTL_SECONDS,
    MARKET_DATA_RETRY_ATTEMPTS,
    MARKET_DATA_RETRY_INITIAL_DELAY_SECONDS,
)
from crypto_predictor.exchange import build_exchange
from crypto_predictor.infrastructure.cache import default_cache
from crypto_predictor.infrastructure.observability import observed
from crypto_predictor.infrastructure.retry import retry_call
from crypto_predictor.models import Candle, MarketData
from crypto_predictor.sentiment import fetch_fear_greed_index
from crypto_predictor.time_utils import to_iso, utc_now


def fetch_latest_ohlcv(
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    limit: int = DEFAULT_LIMIT,
    exchange_id: str = DEFAULT_EXCHANGE_ID,
) -> MarketData:
    """使用 ccxt 从 Binance 获取最新 K 线数据。"""

    cache_key = f"ohlcv:{exchange_id}:{symbol}:{timeframe}:{limit}"
    cached = default_cache.get(cache_key)
    if cached is not None:
        return cached

    exchange = build_exchange(exchange_id)
    with observed("market_data.fetch_ohlcv", exchange_id=exchange_id, symbol=symbol, timeframe=timeframe, limit=limit):
        raw_candles = retry_call(
            lambda: exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit),
            attempts=MARKET_DATA_RETRY_ATTEMPTS,
            initial_delay_seconds=MARKET_DATA_RETRY_INITIAL_DELAY_SECONDS,
        )

    if not raw_candles:
        raise RuntimeError(f"没有获取到 {exchange_id} {symbol} {timeframe} K 线数据")

    candles = [
        Candle(
            timestamp_ms=int(item[0]),
            open=float(item[1]),
            high=float(item[2]),
            low=float(item[3]),
            close=float(item[4]),
            volume=float(item[5]),
        )
        for item in raw_candles
    ]

    market_data = MarketData(
        exchange=exchange_id,
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        current_price=float(candles[-1].close),
        fetched_at=to_iso(utc_now()),
        fear_greed_index=fetch_fear_greed_index(),
    )
    default_cache.set(cache_key, market_data, MARKET_DATA_CACHE_TTL_SECONDS)
    return market_data


def compact_market_data_for_prompt(market_data: MarketData) -> dict[str, Any]:
    """只把必要字段传给 AI，减少 token 与噪声。"""

    payload = {
        "exchange": market_data.exchange,
        "symbol": market_data.symbol,
        "timeframe": market_data.timeframe,
        "current_price": market_data.current_price,
        "fetched_at": market_data.fetched_at,
        "candles": [asdict(candle) for candle in market_data.candles],
    }
    if market_data.fear_greed_index is not None:
        payload["sentiment"] = {
            "crypto_fear_greed_index": asdict(market_data.fear_greed_index),
            "interpretation": "0 means extreme fear, 100 means extreme greed.",
        }
    return payload
