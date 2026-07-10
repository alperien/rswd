from __future__ import annotations

import os
from pathlib import Path

from click.testing import CliRunner

from rswd.__main__ import cli
from rswd.db.schema import ensure_schema
from tests.conftest import write_test_config


def test_library_status_empty(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "library", "status"])
    assert result.exit_code == 0
    assert "Artists:" in result.output
    assert "Albums:" in result.output
    assert "Tracks:" in result.output


def test_library_scan_directory(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    music = tmp_path / "music"
    music.mkdir()
    cfg = write_test_config(tmp_path / "config", db, str(music))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "library", "scan", "--path", str(music)])
    assert result.exit_code == 0
    assert "Scanned:" in result.output


def test_library_scan_default_path(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    music = tmp_path / "music"
    music.mkdir()
    cfg = write_test_config(tmp_path / "config", db, str(music))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "library", "scan"])
    assert result.exit_code == 0
    assert "Scanned:" in result.output


def test_library_prune(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "library", "prune"])
    assert result.exit_code == 0
    assert "Pruned" in result.output


def test_library_import_dry_run(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    music = tmp_path / "source_music"
    music.mkdir()
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "library", "import", str(music), "--dry-run"])
    assert result.exit_code == 0
    assert "Dry-run scan of" in result.output


def test_library_import_imports_files(tmp_path):
    db = str(tmp_path / "library.db")
    ensure_schema(db)
    music = tmp_path / "source_music"
    music.mkdir()
    fp = music / "track.flac"
    import struct
    sinfo = struct.pack(">HH", 4096, 4096)
    sinfo += struct.pack(">I", 0)[1:4]
    sinfo += struct.pack(">I", 0)[1:4]
    sinfo += struct.pack(">H", 44100 >> 4)
    sinfo += struct.pack("B", 0x42)
    sinfo += struct.pack(">Q", 15 << 36)[3:8]
    sinfo += b"\x00" * 16
    hdr = struct.pack("B", 0x00) + struct.pack(">I", 34)[1:4]
    last = struct.pack("B", 0x81) + struct.pack(">I", 0)[1:4]
    fp.write_bytes(b"fLaC" + hdr + sinfo + last)
    from mutagen.flac import FLAC
    audio = FLAC(str(fp))
    audio.add_tags()
    audio["title"] = "Test Song"
    audio["artist"] = "Test Artist"
    audio["album"] = "Test Album"
    audio.save()
    cfg = write_test_config(tmp_path / "config", db, str(tmp_path / "music"))
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", cfg, "library", "import", str(music)])
    assert result.exit_code == 0
    assert "Imported:" in result.output
