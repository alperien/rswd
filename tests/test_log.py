from __future__ import annotations

import logging
from pathlib import Path

import pytest
from rich.logging import RichHandler

from rswd.log import setup_logging


@pytest.fixture(autouse=True)
def _cleanup_logger():
    yield
    root = logging.getLogger("rswd")
    for h in root.handlers[:]:
        h.close()
        root.removeHandler(h)
    root.setLevel(logging.NOTSET)


def test_setup_logging_creates_dir(tmp_path):
    log_dir = tmp_path / "logs"
    logger = setup_logging(log_dir, level="DEBUG", verbose=True)
    assert log_dir.is_dir()
    assert (log_dir / "rswd.log").exists()


def test_setup_logging_daemon_mode(tmp_path):
    log_dir = tmp_path / "daemon_logs"
    logger = setup_logging(log_dir, daemon_mode=True)
    assert log_dir.is_dir()
    assert not any(isinstance(h, RichHandler) for h in logger.handlers)


def test_setup_logging_quiet(tmp_path):
    log_dir = tmp_path / "quiet_logs"
    logger = setup_logging(log_dir, level="WARNING", verbose=False)
    assert isinstance(logger, logging.Logger)
    assert logger.name == "rswd"
    assert logger.level == logging.WARNING
