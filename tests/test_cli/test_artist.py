import os
from pathlib import Path

from click.testing import CliRunner

from rswd.__main__ import cli
from rswd.db.schema import ensure_schema
from tests.conftest import write_test_config


def test_artist_list_empty(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "artist", "list"])
    assert result.exit_code == 0, result.output
    assert "No artists found" in result.output


def test_artist_add_and_list(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "artist", "add", "TestArtist"])
    assert result.exit_code == 0, result.output
    assert "Added" in result.output
    result = runner.invoke(cli, ["--config", cfg, "artist", "list"])
    assert result.exit_code == 0, result.output
    assert "TestArtist" in result.output


def test_artist_remove(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    r = runner.invoke(cli, ["--config", cfg, "artist", "add", "ToRemove"])
    assert r.exit_code == 0, r.output
    result = runner.invoke(cli, ["--config", cfg, "artist", "remove", "1"])
    assert result.exit_code == 0, result.output
    assert "Removed" in result.output


def test_artist_monitor_unmonitor(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    r = runner.invoke(cli, ["--config", cfg, "artist", "add", "MArtist", "--monitor"])
    assert r.exit_code == 0, r.output
    result = runner.invoke(cli, ["--config", cfg, "artist", "list", "--monitored"])
    assert result.exit_code == 0, result.output
    assert "MArtist" in result.output
    r = runner.invoke(cli, ["--config", cfg, "artist", "unmonitor", "1"])
    assert r.exit_code == 0, r.output
    result = runner.invoke(cli, ["--config", cfg, "artist", "list", "--unmonitored"])
    assert result.exit_code == 0, result.output
    assert "MArtist" in result.output
