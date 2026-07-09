from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger("rswd.web.download_manager")


class DlStatus(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DownloadTask:
    id: str = ""
    service: str = ""
    service_id: str = ""
    album_title: str = ""
    artist_name: str = ""
    status: DlStatus = DlStatus.QUEUED
    progress: str = ""
    error: Optional[str] = None
    tracks_total: int = 0
    tracks_done: int = 0
    created_at: str = ""
    completed_at: Optional[str] = None


class DownloadManager:
    def __init__(self):
        self._tasks: dict[str, DownloadTask] = {}
        self._lock = threading.Lock()

    def create_task(
        self, service: str, service_id: str, album_title: str, artist_name: str
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        task = DownloadTask(
            id=task_id,
            service=service,
            service_id=service_id,
            album_title=album_title,
            artist_name=artist_name,
            status=DlStatus.QUEUED,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._tasks[task_id] = task
        logger.info("Created download task %s: %s - %s", task_id, artist_name, album_title)
        return task_id

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        with self._lock:
            task = self._tasks.get(task_id)
            return task

    def list_tasks(self) -> list[DownloadTask]:
        with self._lock:
            return list(self._tasks.values())

    def update_task(self, task_id: str, **kwargs):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                for k, v in kwargs.items():
                    if k == "status" and isinstance(v, str):
                        v = DlStatus(v)
                    setattr(task, k, v)
                if kwargs.get("status") in (DlStatus.COMPLETED, DlStatus.FAILED):
                    task.completed_at = datetime.now(timezone.utc).isoformat()
