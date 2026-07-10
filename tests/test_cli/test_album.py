from __future__ import annotations

import os
from pathlib import Path

from click.testing import CliRunner

from rswd.__main__ import cli
from rswd.db.repository import Repository
from rswd.db.schema import ensure_schema
from tests.conftest import write_test_config


def test_album_list_empty(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "album", "list"])
    assert result.exit_code == 0
    assert "No albums found" in result.output


def test_album_list_with_albums(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    repo = Repository(db)
    repo.connect()
    try:
        aid = repo.add_artist("Test Artist")
        repo.add_album(aid, "Test Album", year=2020, service="deezer")
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", cfg, "album", "list"])
        assert result.exit_code == 0
        assert "Test Album" in result.output
        assert "1" in result.output
    finally:
        repo.close()


def test_album_search_shows_results(httpx_mock, tmp_path):
    httpx_mock.add_response(
        json={
            "data": [
                {
                    "id": 12345,
                    "title": "OK Computer",
                    "artist": {"id": 1, "name": "Radiohead"},
                    "release_date": "1997-05-21",
                    "nb_tracks": 12,
                    "type": "album",
                }
            ]
        },
        url="https://api.deezer.com/search/album?q=OK+Computer",
    )
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "album", "search", "OK Computer"])
    assert result.exit_code == 0
    assert "OK Computer" in result.output
    assert "Radiohead" in result.output


def test_album_search_no_results(httpx_mock, tmp_path):
    httpx_mock.add_response(json={"data": []})
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "album", "search", "Nonexistent"])
    assert result.exit_code == 0
    assert "No results" in result.output


def test_album_download_fails_for_missing_album(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "album", "download", "999"])
    # CLI returns 0 even when album not found; it prints a message instead of erroring
    assert result.exit_code == 0
    assert "not found" in result.output


def test_album_download_fails_without_service_id(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    repo = Repository(db)
    repo.connect()
    try:
        aid = repo.add_artist("Test Artist")
        repo.add_album(aid, "Test Album", year=2020)
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", cfg, "album", "download", "1"])
        assert result.exit_code == 0
        assert "no service_id" in result.output.lower()
    finally:
        repo.close()
