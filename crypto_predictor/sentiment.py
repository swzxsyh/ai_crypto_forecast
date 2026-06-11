"""Market sentiment data providers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from crypto_predictor.config import (
    FEAR_GREED_API_URL,
    FEAR_GREED_ENABLED,
    FEAR_GREED_TIMEOUT_SECONDS,
)
from crypto_predictor.models import FearGreedIndex


def fetch_fear_greed_index() -> FearGreedIndex | None:
    """Fetch the latest Crypto Fear & Greed Index snapshot."""

    if not FEAR_GREED_ENABLED:
        return None

    request = urllib.request.Request(
        FEAR_GREED_API_URL,
        headers={"Accept": "application/json", "User-Agent": "AiCrypto/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=FEAR_GREED_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None

    return parse_fear_greed_payload(payload)


def parse_fear_greed_payload(payload: dict[str, Any]) -> FearGreedIndex | None:
    """Parse alternative.me /fng/ response payload."""

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None

    latest = data[0]
    if not isinstance(latest, dict):
        return None

    try:
        value = int(latest.get("value"))
    except (TypeError, ValueError):
        return None

    time_until_update_raw = latest.get("time_until_update")
    try:
        time_until_update = int(time_until_update_raw) if time_until_update_raw not in {None, ""} else None
    except (TypeError, ValueError):
        time_until_update = None

    return FearGreedIndex(
        value=value,
        classification=str(latest.get("value_classification") or ""),
        timestamp=str(latest.get("timestamp") or ""),
        time_until_update=time_until_update,
    )
