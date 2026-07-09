import os
from pathlib import Path

import tomllib
from click.testing import CliRunner

from rswd.__main__ import cli
from rswd.db.schema import ensure_schema


def write_test_config(config_dir: Path, db_path: str, download_path: str):
    config_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "core": {
            "download_path": download_path,
            "library_db": db_path,
            "jobs_db": str(Path(db_path).parent / "jobs.db"),
        }
    }
    lines = ["[core]"]
    for k, v in data["core"].items():
        lines.append(f'{k} = "{v.replace(os.sep, "/")}"')
    (config_dir / "config.toml").write_text("\n".join(lines))
    return str(config_dir / "config.toml")


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
    assert "TestArtist" in result.output


def test_artist_remove(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    runner.invoke(cli, ["--config", cfg, "artist", "add", "ToRemove"])
    result = runner.invoke(cli, ["--config", cfg, "artist", "remove", "1"])
    assert result.exit_code == 0, result.output
    assert "Removed" in result.output


def test_artist_monitor_unmonitor(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    runner.invoke(cli, ["--config", cfg, "artist", "add", "MArtist", "--monitor"])
    result = runner.invoke(cli, ["--config", cfg, "artist", "list", "--monitored"])
    assert "MArtist" in result.output
    runner.invoke(cli, ["--config", cfg, "artist", "unmonitor", "1"])
    result = runner.invoke(cli, ["--config", cfg, "artist", "list", "--unmonitored"])
    assert "MArtist" in result.output
