"""Web 可控的自动任务管理器。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from crypto_predictor.auto_runner import run_auto_cycle
from crypto_predictor.config import (
    AUTO_RUN_CHECK_ACCURACY,
    AUTO_RUN_EXECUTE_LIVE,
    AUTO_RUN_EXECUTE_PAPER,
    AUTO_RUN_INTERVAL_SECONDS,
    AUTO_RUN_MODEL_TYPE,
    AUTO_RUN_PREDICT_ALL_SYMBOLS,
)
from crypto_predictor.config import DB_PATH, DEFAULT_LIMIT, DEFAULT_SYMBOL, DEFAULT_SYMBOLS, DEFAULT_TIMEFRAME
from crypto_predictor.database import get_overall_accuracy, save_auto_run_log
from crypto_predictor.infrastructure.task_status import default_task_status_store
from crypto_predictor.time_utils import to_iso, utc_now


@dataclass(frozen=True)
class AutoTaskConfig:
    """自动任务运行参数。"""

    interval_seconds: int
    symbols: tuple[str, ...]
    timeframe: str
    limit: int
    model_type: str
    execute_paper: bool
    check_accuracy: bool
    execute_live: bool = False
    max_margin_per_trade: float | None = None
    max_cycles: int = 0
    allow_overlap: bool = False


class AutoTaskManager:
    """管理后台自动任务线程，支持启动、停止、状态查询。"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._started_at: str | None = None
        self._last_cycle_started_at: str | None = None
        self._last_cycle_finished_at: str | None = None
        self._last_log_id: int | None = None
        self._last_error: str | None = None
        self._completed_cycles = 0
        self._config: AutoTaskConfig | None = None

    def start(self, config: AutoTaskConfig) -> dict[str, Any]:
        """启动自动任务；已在运行则返回当前状态。"""

        config = self._normalize_config(config)

        with self._lock:
            if self._running:
                return {"started": False, "reason": "already_running", "status": self.get_status()}

            self._stop_event.clear()
            self._running = True
            self._started_at = to_iso(utc_now())
            self._last_error = None
            self._completed_cycles = 0
            self._config = config
            default_task_status_store.set(
                "auto_task",
                "running",
                started_at=self._started_at,
                symbols=list(config.symbols),
                timeframe=config.timeframe,
                interval_seconds=config.interval_seconds,
                max_cycles=config.max_cycles,
                allow_overlap=config.allow_overlap,
                completed_cycles=self._completed_cycles,
            )

            self._thread = threading.Thread(
                target=self._run_loop,
                name="crypto-auto-task-manager",
                args=(config,),
                daemon=True,
            )
            self._thread.start()

        return {"started": True, "status": self.get_status()}

    def stop(self) -> dict[str, Any]:
        """停止自动任务线程。"""

        with self._lock:
            thread = self._thread
            if not self._running or thread is None:
                return {"stopped": False, "reason": "not_running", "status": self.get_status()}
            self._stop_event.set()

        thread.join(timeout=0.2)

        with self._lock:
            if thread.is_alive():
                default_task_status_store.set("auto_task", "stopping")
                return {"stopped": True, "stopping": True, "status": self.get_status()}
            self._running = False
            self._thread = None
            default_task_status_store.set("auto_task", "stopped")

        return {"stopped": True, "status": self.get_status()}

    def get_status(self) -> dict[str, Any]:
        """获取当前自动任务状态。"""

        with self._lock:
            config = self._config
            return {
                "running": self._running,
                "started_at": self._started_at,
                "last_cycle_started_at": self._last_cycle_started_at,
                "last_cycle_finished_at": self._last_cycle_finished_at,
                "last_log_id": self._last_log_id,
                "last_error": self._last_error,
                "completed_cycles": self._completed_cycles,
                "config": {
                    "interval_seconds": config.interval_seconds if config else None,
                    "symbols": list(config.symbols) if config else [],
                    "timeframe": config.timeframe if config else None,
                    "limit": config.limit if config else None,
                    "model_type": config.model_type if config else None,
                    "execute_paper": config.execute_paper if config else None,
                    "execute_live": config.execute_live if config else None,
                    "check_accuracy": config.check_accuracy if config else None,
                    "max_margin_per_trade": config.max_margin_per_trade if config else None,
                    "max_cycles": config.max_cycles if config else 0,
                    "allow_overlap": config.allow_overlap if config else False,
                },
            }

    def _run_loop(self, config: AutoTaskConfig) -> None:
        if config.allow_overlap:
            self._run_overlapping_loop(config)
        else:
            self._run_serial_loop(config)

        with self._lock:
            self._running = False
        default_task_status_store.set("auto_task", "stopped")

    def _run_serial_loop(self, config: AutoTaskConfig) -> None:
        while not self._stop_event.is_set():
            cycle_started = utc_now()
            cycle_finished = self._run_cycle_once(config, cycle_started)

            if config.max_cycles > 0 and self._completed_cycles >= config.max_cycles:
                break

            elapsed = (cycle_finished - cycle_started).total_seconds()
            wait_seconds = max(0.0, config.interval_seconds - elapsed)
            if self._stop_event.wait(timeout=wait_seconds):
                break

    def _run_overlapping_loop(self, config: AutoTaskConfig) -> None:
        launched_cycles = 0
        active_threads: list[threading.Thread] = []

        while not self._stop_event.is_set():
            active_threads = [thread for thread in active_threads if thread.is_alive()]
            if config.max_cycles > 0 and launched_cycles >= config.max_cycles:
                break

            launched_cycles += 1
            thread = threading.Thread(
                target=self._run_cycle_once,
                name=f"crypto-auto-cycle-{launched_cycles}",
                args=(config,),
                daemon=True,
            )
            thread.start()
            active_threads.append(thread)

            if self._stop_event.wait(timeout=config.interval_seconds):
                break

        while active_threads and not self._stop_event.is_set():
            active_threads = [thread for thread in active_threads if thread.is_alive()]
            if active_threads:
                time.sleep(0.2)

    def _run_cycle_once(self, config: AutoTaskConfig, cycle_started=None):
        cycle_started = cycle_started or utc_now()
        try:
            self._set_cycle_started(to_iso(cycle_started))
            default_task_status_store.set(
                "auto_task",
                "cycle_running",
                cycle_started_at=to_iso(cycle_started),
                symbols=list(config.symbols),
                timeframe=config.timeframe,
                completed_cycles=self._completed_cycles,
                max_cycles=config.max_cycles,
                allow_overlap=config.allow_overlap,
            )

            log_payload: dict[str, Any] = {
                "cycle_started_at": to_iso(cycle_started),
                "interval_seconds": config.interval_seconds,
                "symbols": list(config.symbols),
                "timeframe": config.timeframe,
                "kline_limit": config.limit,
                "model_type": config.model_type,
                "execute_paper": config.execute_paper,
                "execute_live": config.execute_live,
                "check_accuracy": config.check_accuracy,
                "details": {},
            }

            try:
                cycle_result = run_auto_cycle(
                    symbols=config.symbols,
                    timeframe=config.timeframe,
                    limit=config.limit,
                    model_type=config.model_type,
                    execute_paper=config.execute_paper,
                    execute_live=config.execute_live,
                    check_accuracy=config.check_accuracy,
                    max_margin_per_trade=config.max_margin_per_trade,
                )

                paper_orders = cycle_result.get("paper_orders", [])
                paper_ok = sum(1 for item in paper_orders if item.get("status") == "ok")
                paper_error = sum(1 for item in paper_orders if item.get("status") != "ok")
                live_orders = cycle_result.get("live_orders", [])
                live_ok = sum(1 for item in live_orders if item.get("status") == "ok")
                live_error = sum(1 for item in live_orders if item.get("status") != "ok")
                accuracy_check = cycle_result.get("accuracy_check") or {}
                overall = get_overall_accuracy(db_path=self.db_path)

                log_payload.update(
                    {
                        "status": "ok",
                        "predictions_created": cycle_result.get("predictions_created", 0),
                        "paper_orders_total": len(paper_orders),
                        "paper_orders_ok": paper_ok,
                        "paper_orders_error": paper_error,
                        "live_orders_total": len(live_orders),
                        "live_orders_ok": live_ok,
                        "live_orders_error": live_error,
                        "checked_count": accuracy_check.get("checked_count"),
                        "accurate_count": accuracy_check.get("accurate_count"),
                        "direction_accuracy": accuracy_check.get("direction_accuracy"),
                        "overall_checked": overall.get("total_checked"),
                        "overall_accurate": overall.get("total_accurate"),
                        "overall_accuracy": overall.get("overall_accuracy"),
                        "details": cycle_result,
                    }
                )
                self._set_last_error(None)
                default_task_status_store.set("auto_task", "cycle_succeeded")
            except Exception as exc:  # noqa: BLE001
                log_payload.update(
                    {
                        "status": "error",
                        "predictions_created": 0,
                        "paper_orders_total": 0,
                        "paper_orders_ok": 0,
                        "paper_orders_error": 0,
                        "checked_count": None,
                        "accurate_count": None,
                        "direction_accuracy": None,
                        "overall_checked": None,
                        "overall_accurate": None,
                        "overall_accuracy": None,
                        "error_message": str(exc),
                        "details": {"error": str(exc)},
                    }
                )
                self._set_last_error(str(exc))
                default_task_status_store.set("auto_task", "cycle_failed", error=str(exc))

            cycle_finished = utc_now()
            log_payload["cycle_finished_at"] = to_iso(cycle_finished)
            log_id = save_auto_run_log(log_payload, db_path=self.db_path)
            self._set_cycle_finished(to_iso(cycle_finished), log_id)
            self._increment_completed_cycles()
            return cycle_finished
        except Exception:
            cycle_finished = utc_now()
            self._set_cycle_finished(to_iso(cycle_finished), self._last_log_id or 0)
            raise

    def _normalize_config(self, config: AutoTaskConfig) -> AutoTaskConfig:
        symbols = tuple(item.strip() for item in config.symbols if item and item.strip())
        if not symbols:
            symbols = DEFAULT_SYMBOLS

        return AutoTaskConfig(
            interval_seconds=max(10, int(config.interval_seconds)),
            symbols=symbols,
            timeframe=(config.timeframe or DEFAULT_TIMEFRAME).strip() or DEFAULT_TIMEFRAME,
            limit=max(1, int(config.limit)),
            model_type=(config.model_type or AUTO_RUN_MODEL_TYPE).strip() or AUTO_RUN_MODEL_TYPE,
            execute_paper=bool(config.execute_paper),
            execute_live=bool(config.execute_live),
            check_accuracy=bool(config.check_accuracy),
            max_margin_per_trade=config.max_margin_per_trade,
            max_cycles=max(0, int(config.max_cycles or 0)),
            allow_overlap=bool(config.allow_overlap),
        )

    def _set_cycle_started(self, started_at: str) -> None:
        with self._lock:
            self._last_cycle_started_at = started_at

    def _set_cycle_finished(self, finished_at: str, log_id: int) -> None:
        with self._lock:
            self._last_cycle_finished_at = finished_at
            self._last_log_id = log_id

    def _increment_completed_cycles(self) -> None:
        with self._lock:
            self._completed_cycles += 1

    def _set_last_error(self, error: str | None) -> None:
        with self._lock:
            self._last_error = error


def build_default_auto_config() -> AutoTaskConfig:
    """构建默认自动任务配置。"""

    return AutoTaskConfig(
        interval_seconds=AUTO_RUN_INTERVAL_SECONDS,
        symbols=DEFAULT_SYMBOLS if AUTO_RUN_PREDICT_ALL_SYMBOLS else (DEFAULT_SYMBOL,),
        timeframe=DEFAULT_TIMEFRAME,
        limit=DEFAULT_LIMIT,
        model_type=AUTO_RUN_MODEL_TYPE,
        execute_paper=AUTO_RUN_EXECUTE_PAPER,
        execute_live=AUTO_RUN_EXECUTE_LIVE,
        check_accuracy=AUTO_RUN_CHECK_ACCURACY,
        max_cycles=0,
        allow_overlap=False,
    )
