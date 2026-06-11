"""全局日志初始化：每日切割，自动清理超期日志文件。"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def setup_logging(
    log_dir: str = "logs",
    level: str = "INFO",
    retention_days: int = 30,
) -> None:
    """配置根 Logger：TimedRotatingFileHandler（每日午夜 UTC 切割）+ StreamHandler。

    参数：
        log_dir         日志目录，不存在时自动创建。
        level           日志级别字符串，例如 "INFO" / "DEBUG"。
        retention_days  保留最近 N 天的日志文件，更早的自动删除。
    """

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    file_fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    stream_fmt = logging.Formatter("%(levelname)-8s %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # 避免重复添加 handler（Flask debug reloader 会 import 两次）
    existing_types = [type(h) for h in root.handlers]

    if logging.handlers.TimedRotatingFileHandler not in existing_types:
        fh = logging.handlers.TimedRotatingFileHandler(
            filename=log_path / "app.log",
            when="midnight",
            interval=1,
            backupCount=retention_days,
            encoding="utf-8",
            utc=True,
        )
        fh.setFormatter(file_fmt)
        root.addHandler(fh)

    # StreamHandler（只加一个，避免重复输出到终端）
    has_stream = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    )
    if not has_stream:
        sh = logging.StreamHandler()
        sh.setFormatter(stream_fmt)
        root.addHandler(sh)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
