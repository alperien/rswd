from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    log_dir: Path,
    level: str = "INFO",
    verbose: bool = False,
    daemon_mode: bool = False,
) -> logging.Logger:
    root = logging.getLogger("rswd")
    root.setLevel(logging.DEBUG if verbose else level)
    root.handlers.clear()

    if not daemon_mode:
        console = RichHandler(
            rich_tracebacks=True,
            markup=True,
            show_path=False,
        )
        console.setLevel(logging.DEBUG if verbose else logging.INFO)
        root.addHandler(console)

    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "rswd.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("streamrip").setLevel(logging.WARNING)
    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return root
