"""Market sentiment data providers."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from crypto_predictor.config import (
    FEAR_GREED_API_URL,
    FEAR_GREED_ENABLED,
    FEAR_GREED_TIMEOUT_SECONDS,
)
from crypto_predictor.models import FearGreedIndex

logger = logging.getLogger(__name__)


def fetch_fear_greed_index() -> FearGreedIndex | None:
    """Fetch the latest Crypto Fear & Greed Index snapshot."""

    if not FEAR_GREED_ENABLED:
        logger.info("Fear & Greed Index disabled; using pure OHLCV mode")
        return None

    request = urllib.request.Request(
        FEAR_GREED_API_URL,
        headers={"Accept": "application/json", "User-Agent": "AiCrypto/1.0"},
    )

    try:
        logger.info("Fetching Crypto Fear & Greed Index")
        with urllib.request.urlopen(request, timeout=FEAR_GREED_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = parse_fear_greed_payload(payload)
        if result is None:
            logger.warning("Fear & Greed Index payload could not be parsed; using pure OHLCV mode")
        else:
            logger.info(
                "Fear & Greed Index fetched: value=%s classification=%s",
                result.value,
                result.classification,
            )
        return result
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        logger.warning("Fear & Greed Index fetch failed: %s; using pure OHLCV mode", exc)
        return None


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
