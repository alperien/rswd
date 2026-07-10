"""Scheduler module - kept for future daemon/scheduling use."""
from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]

logger = logging.getLogger("rswd.scheduler")


@dataclass
class DaemonState:
    running: bool = False
    started_at: Optional[str] = None
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=1000))


_scheduler: BackgroundScheduler | None = None
_state: DaemonState = DaemonState()
_lock = threading.Lock()


def get_state() -> DaemonState:
    with _lock:
        return DaemonState(
            running=_state.running,
            started_at=_state.started_at,
            logs=deque(_state.logs, maxlen=1000),
        )


def start() -> bool:
    global _scheduler, _state
    with _lock:
        if _scheduler and _scheduler.running:
            logger.warning("Daemon already running")
            return False
        try:
            _scheduler = BackgroundScheduler(daemon=True)
            _scheduler.start()
        except Exception:
            _scheduler = None
            raise
        _state.running = True
        _state.started_at = datetime.now(timezone.utc).isoformat()
        _state.logs.append(f"[{_state.started_at}] Daemon started")
        logger.info("Daemon started")
        return True


def stop() -> bool:
    global _scheduler, _state
    with _lock:
        if not _scheduler or not _scheduler.running:
            logger.warning("Daemon not running")
            return False
        _scheduler.shutdown(wait=True)
        _scheduler = None
        _state.running = False
        _state.started_at = None
        ts = datetime.now(timezone.utc).isoformat()
        _state.logs.append(f"[{ts}] Daemon stopped")
        logger.info("Daemon stopped")
        return True


def add_log(message: str):
    with _lock:
        ts = datetime.now(timezone.utc).isoformat()
        _state.logs.append(f"[{ts}] {message}")
