"""Trading execution orchestration."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from crypto_predictor.broker.binance_broker import execute_binance_order
from crypto_predictor.broker.models import ExecutionMode, OrderRequest, OrderResult
from crypto_predictor.broker.paper_broker import execute_paper_order
from crypto_predictor.broker.risk_guard import validate_order_request
from crypto_predictor.config import DB_PATH, RISK_MAX_MARGIN_PER_TRADE, TRADING_MODE
from crypto_predictor.infrastructure.persistence.repository_factory import get_repository


def execute_prediction_order(
    prediction_id: int | None = None,
    mode: ExecutionMode | None = None,
    confirm: str | None = None,
    max_margin_per_trade: float | None = None,
    db_path: str = DB_PATH,
) -> dict[str, Any]:
    """Convert a prediction row into a paper or live order."""

    repo = get_repository()
    if hasattr(repo, "db_path"):
        repo.db_path = db_path
    row = repo.get_prediction_by_id(prediction_id) if prediction_id else repo.get_latest_prediction()
    if row is None:
        raise RuntimeError("No executable prediction record found")

    execution_mode = mode or normalize_mode(TRADING_MODE)
    request = build_order_request(row, execution_mode)
    if execution_mode == "paper":
        request = cap_paper_margin(request, max_margin_per_trade)
    validate_order_request(request, max_margin_override=max_margin_per_trade)

    if execution_mode == "paper":
        result = execute_paper_order(request)
    else:
        result = execute_binance_order(request, confirm=confirm)

    trade_order_id = repo.save_trade_order(prediction_id=int(row["id"]), result=result)
    return {
        "trade_order_id": trade_order_id,
        "prediction_id": int(row["id"]),
        "result": result.__dict__ | {"raw_response": result.raw_response},
    }


def build_order_request(row: Any, mode: ExecutionMode) -> OrderRequest:
    """Build an order request from a prediction row."""

    entry_price = float(row["entry_price"] or row["current_price"])
    notional_value = float(row["notional_value"] or 0)
    amount = notional_value / entry_price if entry_price > 0 else 0

    return OrderRequest(
        prediction_id=int(row["id"]),
        symbol=str(row["symbol"]),
        position_side=str(row["position_side"]),
        margin_amount=float(row["margin_amount"] or 0),
        leverage=int(row["leverage"] or 0),
        entry_price=entry_price,
        take_profit_price=float(row["take_profit_price"] or 0),
        stop_loss_price=float(row["stop_loss_price"] or 0),
        notional_value=notional_value,
        amount=amount,
        mode=mode,
    )


def cap_paper_margin(request: OrderRequest, max_margin_per_trade: float | None = None) -> OrderRequest:
    effective_max_margin = max_margin_per_trade if max_margin_per_trade is not None else RISK_MAX_MARGIN_PER_TRADE
    if request.margin_amount <= effective_max_margin:
        return request

    margin_amount = effective_max_margin
    notional_value = margin_amount * request.leverage
    amount = notional_value / request.entry_price if request.entry_price > 0 else 0
    return replace(
        request,
        margin_amount=margin_amount,
        notional_value=notional_value,
        amount=amount,
    )


def normalize_mode(value: str) -> ExecutionMode:
    """Normalize execution mode."""

    if value == "paper":
        return "paper"
    if value == "live":
        return "live"
    raise ValueError(f"Unsupported trading mode: {value}")


def result_to_json(result: OrderResult) -> str:
    """Serialize an order result."""

    return json.dumps(result.__dict__, ensure_ascii=False, default=str)
