from __future__ import annotations

import logging
import os
import stat
import sys
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
    try:
        root.setLevel(logging.DEBUG if verbose else level)
    except ValueError:
        logging.warning("Invalid log level %r, falling back to INFO", level)
        root.setLevel(logging.INFO)
    for handler in root.handlers[:]:
        try:
            handler.close()
        except Exception as e:
            root.debug("Error closing handler: %s", e)
    root.handlers.clear()

    if not daemon_mode:
        # Note: rich_tracebacks=True may include local variables in
        # tracebacks, which could inadvertently leak sensitive data
        # such as tokens, passwords, or file paths.
        console = RichHandler(
            rich_tracebacks=True,
            markup=True,
            show_path=False,
        )
        console.setLevel(logging.DEBUG if verbose else logging.INFO)
        root.addHandler(console)

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "rswd.log"
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    if sys.platform != "win32":
        try:
            os.chmod(log_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("streamrip").setLevel(logging.WARNING)
    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return root
