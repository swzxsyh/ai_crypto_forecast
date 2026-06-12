"""Market data fetching and compact prompt payload helpers."""

from __future__ import annotations

from dataclasses import asdict
from statistics import mean
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
    """Fetch latest OHLCV candles from the configured exchange."""

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
        raise RuntimeError(f"No OHLCV data returned for {exchange_id} {symbol} {timeframe}")

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
    """Build a compact but structured payload for the AI prompt."""

    payload = {
        "exchange": market_data.exchange,
        "symbol": market_data.symbol,
        "timeframe": market_data.timeframe,
        "current_price": market_data.current_price,
        "fetched_at": market_data.fetched_at,
        "candles": [asdict(candle) for candle in market_data.candles],
        "technical_summary": build_technical_summary(market_data.candles),
    }
    if market_data.fear_greed_index is not None:
        payload["sentiment"] = {
            "crypto_fear_greed_index": asdict(market_data.fear_greed_index),
            "interpretation": {
                "scale": "0 means extreme fear; 100 means extreme greed.",
                "time_granularity": "Daily macro sentiment only. For 1h prediction, treat it as background context, not a direct trade signal.",
                "extreme_fear": "Value < 25 means risk-off. It is not a blind long/bottom-fishing signal. Use it as reversal support only when OHLCV shows bottoming, volume expansion, or severe RSI oversold rebound.",
                "extreme_greed": "Value > 75 means overheated. Be alert to long liquidation wicks or pullbacks unless OHLCV shows a high-volume breakout.",
                "weighting_rule": "Short-term decision weight should lean about 70% on OHLCV, RSI, and volume structure; sentiment is auxiliary macro background.",
            },
        }
    return payload


def build_technical_summary(candles: list[Candle]) -> dict[str, Any]:
    """Compute lightweight indicators from the candles for prompt grounding."""

    closes = [candle.close for candle in candles]
    volumes = [candle.volume for candle in candles]
    if not candles or not closes:
        return {}

    last = candles[-1]
    first = candles[0]
    recent = candles[-6:]
    previous = candles[-12:-6]
    recent_volumes = [candle.volume for candle in recent]
    previous_volumes = [candle.volume for candle in previous]

    rsi_14 = calculate_rsi(closes, period=14)
    price_change_pct = pct_change(first.open, last.close)
    recent_change_pct = pct_change(recent[0].open, recent[-1].close) if recent else None
    last_candle_change_pct = pct_change(last.open, last.close)
    recent_volume_avg = mean(recent_volumes) if recent_volumes else None
    previous_volume_avg = mean(previous_volumes) if previous_volumes else None
    volume_ratio = (
        recent_volume_avg / previous_volume_avg
        if recent_volume_avg is not None and previous_volume_avg not in {None, 0}
        else None
    )

    return {
        "rsi_14": round(rsi_14, 2) if rsi_14 is not None else None,
        "price_change_pct_over_payload": round(price_change_pct, 6) if price_change_pct is not None else None,
        "recent_6_candle_change_pct": round(recent_change_pct, 6) if recent_change_pct is not None else None,
        "last_candle_change_pct": round(last_candle_change_pct, 6) if last_candle_change_pct is not None else None,
        "recent_6_volume_avg": round(recent_volume_avg, 6) if recent_volume_avg is not None else None,
        "previous_6_volume_avg": round(previous_volume_avg, 6) if previous_volume_avg is not None else None,
        "recent_vs_previous_volume_ratio": round(volume_ratio, 4) if volume_ratio is not None else None,
        "recent_higher_closes": count_higher_closes(recent),
        "recent_lower_closes": count_lower_closes(recent),
    }


def calculate_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None

    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(closes[-period - 1 : -1], closes[-period:]):
        delta = current - previous
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))

    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def pct_change(start: float, end: float) -> float | None:
    if start == 0:
        return None
    return (end - start) / start


def count_higher_closes(candles: list[Candle]) -> int:
    return sum(1 for previous, current in zip(candles, candles[1:]) if current.close > previous.close)


def count_lower_closes(candles: list[Candle]) -> int:
    return sum(1 for previous, current in zip(candles, candles[1:]) if current.close < previous.close)
