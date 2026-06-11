"""Backtesting module boundary.

This module intentionally starts small: it defines the result shape and a
placeholder runner. A future implementation can replay historical candles,
prediction snapshots, fees, slippage, and execution rules without changing the
web or prediction layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BacktestResult:
    trades: int
    win_rate: float | None
    pnl: float
    details: dict[str, Any]


def run_backtest(*, symbol: str, timeframe: str, strategy_name: str = "latest") -> BacktestResult:
    return BacktestResult(
        trades=0,
        win_rate=None,
        pnl=0.0,
        details={
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy_name": strategy_name,
            "status": "not_implemented",
        },
    )
