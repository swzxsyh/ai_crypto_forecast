"""系统内共享的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Direction = Literal["UP", "DOWN", "SIDEWAYS"]
PositionSide = Literal["LONG", "SHORT", "NO_TRADE"]
ModelType = Literal["openai", "anthropic"]


@dataclass(frozen=True)
class Candle:
    """单根 K 线，timestamp_ms 使用交易所返回的毫秒时间戳。"""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class FearGreedIndex:
    """Crypto Fear & Greed Index snapshot."""

    value: int
    classification: str
    timestamp: str
    time_until_update: int | None = None
    source: str = "alternative.me"


@dataclass(frozen=True)
class MarketData:
    """传给 AI 的市场数据快照。"""

    exchange: str
    symbol: str
    timeframe: str
    candles: list[Candle]
    current_price: float
    fetched_at: str
    fear_greed_index: FearGreedIndex | None = None


@dataclass(frozen=True)
class Prediction:
    """AI 预测结果与系统计算后的模拟合约方案。"""

    direction: Direction
    target_price: float
    confidence: int
    position_side: PositionSide
    margin_amount: float
    leverage: int
    take_profit_price: float
    stop_loss_price: float
    entry_price: float | None = None
    notional_value: float | None = None
    expected_profit: float | None = None
    expected_loss: float | None = None
    risk_reward_ratio: float | None = None
