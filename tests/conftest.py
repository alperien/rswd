from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from rswd.config import ConfigData, load_config
from rswd.db.repository import Repository
from rswd.db.schema import ensure_schema


def write_test_config(config_dir: Path, db_path: str, download_path: str):
    config_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "[core]",
        f'download_path = "{download_path.replace(os.sep, "/")}"',
        f'library_db = "{db_path.replace(os.sep, "/")}"',
        f'jobs_db = "{str(Path(db_path).parent / "jobs.db").replace(os.sep, "/")}"',
    ]
    (config_dir / "config.toml").write_text("\n".join(lines))
    return str(config_dir / "config.toml")


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
def repo(db_path: str, request) -> Repository:
    r = Repository(db_path)
    r.connect()
    request.addfinalizer(r.close)
    return r


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()
