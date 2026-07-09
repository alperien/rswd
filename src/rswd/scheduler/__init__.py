from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]

logger = logging.getLogger("rswd.scheduler")


@dataclass
class DaemonState:
    running: bool = False
    started_at: Optional[str] = None
    logs: list[str] = field(default_factory=list)


_scheduler: BackgroundScheduler | None = None
_state: DaemonState = DaemonState()


def get_state() -> DaemonState:
    return _state


def start(config: object = None) -> bool:
    global _scheduler, _state
    if _scheduler and _scheduler.running:
        logger.warning("Daemon already running")
        return False
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.start()
    _state.running = True
    _state.started_at = datetime.now(timezone.utc).isoformat()
    _state.logs.append(f"[{_state.started_at}] Daemon started")
    logger.info("Daemon started")
    return True


def stop() -> bool:
    global _scheduler, _state
    if not _scheduler or not _scheduler.running:
        logger.warning("Daemon not running")
        return False
    _scheduler.shutdown(wait=False)
    _scheduler = None
    _state.running = False
    ts = datetime.now(timezone.utc).isoformat()
    _state.logs.append(f"[{ts}] Daemon stopped")
    logger.info("Daemon stopped")
    return True


def add_log(message: str):
    ts = datetime.now(timezone.utc).isoformat()
    _state.logs.append(f"[{ts}] {message}")
