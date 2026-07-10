from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from rswd.__main__ import cli
from rswd.db.schema import ensure_schema


def write_test_config(config_dir: Path, db_path: str, download_path: str):
    config_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "[core]",
        f'download_path = "{download_path.replace(os.sep, "/")}"',
        f'library_db = "{db_path.replace(os.sep, "/")}"',
        f'jobs_db = "{str(Path(db_path).parent / "jobs.db").replace(os.sep, "/")}"',
        "[daemon]",
        "enabled = true",
        "check_interval_hours = 24",
        "check_at_startup = true",
    ]
    (config_dir / "config.toml").write_text("\n".join(lines))
    return str(config_dir / "config.toml")


def test_daemon_status(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "daemon", "status"])
    assert result.exit_code == 0
    assert "Enabled:" in result.output
    assert "Interval:" in result.output
    assert "Running:" in result.output


@patch("rswd.cli.daemon.default_data_dir")
def test_daemon_stop_when_not_running(mock_data_dir, tmp_path):
    mock_data_dir.return_value = tmp_path
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "daemon", "stop"])
    assert result.exit_code == 0
    assert "not running" in result.output.lower()


def test_daemon_check_monitored_artists(httpx_mock, tmp_path):
    httpx_mock.add_response(
        json={"data": []},
    )
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    from rswd.db.repository import Repository
    repo = Repository(db)
    repo.connect()
    repo.add_artist("Monitored Artist", is_monitored=True)
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "daemon", "check"])
    assert result.exit_code == 0
    assert "checked" in result.output.lower()
