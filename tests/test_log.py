from __future__ import annotations

import logging
from pathlib import Path

from rswd.log import setup_logging


def test_setup_logging_creates_dir(tmp_path):
    log_dir = tmp_path / "logs"
    logger = setup_logging(log_dir, level="DEBUG", verbose=True)
    assert log_dir.is_dir()
    assert (log_dir / "rswd.log").exists() or list(log_dir.glob("*.log"))


def test_setup_logging_daemon_mode(tmp_path):
    log_dir = tmp_path / "daemon_logs"
    logger = setup_logging(log_dir, daemon_mode=True)
    assert log_dir.is_dir()


def test_setup_logging_quiet(tmp_path):
    log_dir = tmp_path / "quiet_logs"
    logger = setup_logging(log_dir, level="WARNING", verbose=False)
    assert isinstance(logger, logging.Logger)
    assert logger.name == "rswd"
