"""时间处理工具。

数据库统一保存 UTC ISO 字符串，避免本地时区和交易所时区混用。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    """返回当前 UTC 时间。"""

    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    """将 datetime 转成 UTC ISO 字符串。"""

    return dt.astimezone(timezone.utc).isoformat()


def from_iso(value: str) -> datetime:
    """从 UTC ISO 字符串还原 datetime。"""

    return datetime.fromisoformat(value).astimezone(timezone.utc)


def parse_timeframe_to_timedelta(timeframe: str) -> timedelta:
    """将 ccxt 常见周期转换为 timedelta，例如 1h -> 1 小时。"""

    unit = timeframe[-1]
    amount = int(timeframe[:-1])

    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    if unit == "w":
        return timedelta(weeks=amount)

    raise ValueError(f"暂不支持的 timeframe: {timeframe}")
