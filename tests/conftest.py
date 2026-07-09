from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from rswd.config import ConfigData, load_config
from rswd.db.repository import Repository
from rswd.db.schema import ensure_schema


@pytest.fixture
def tmp_dir() -> Path:
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def db_path(tmp_dir: Path) -> str:
    db = str(tmp_dir / "test.db")
    ensure_schema(db)
    return db


@pytest.fixture
def repo(db_path: str) -> Repository:
    r = Repository(db_path)
    r.connect()
    return r


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()
