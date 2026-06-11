"""Risk policy boundary."""

from __future__ import annotations

from dataclasses import dataclass

from crypto_predictor.config import RISK_ALLOWED_SYMBOLS, RISK_MAX_LEVERAGE, RISK_MAX_MARGIN_PER_TRADE


@dataclass(frozen=True)
class RiskPolicy:
    max_margin_per_trade: float = RISK_MAX_MARGIN_PER_TRADE
    max_leverage: int = RISK_MAX_LEVERAGE
    allowed_symbols: tuple[str, ...] = RISK_ALLOWED_SYMBOLS

    def clamp_margin(self, value: float) -> float:
        return max(0.0, min(float(value), self.max_margin_per_trade))

    def clamp_leverage(self, value: int) -> int:
        return max(0, min(int(value), self.max_leverage))

    def allows_symbol(self, symbol: str) -> bool:
        return symbol in self.allowed_symbols


default_risk_policy = RiskPolicy()
