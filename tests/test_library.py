from __future__ import annotations

from pathlib import Path

import pytest

from rswd.db.repository import Repository
from rswd.db.schema import ensure_schema
from rswd.library import LibraryScanner


@pytest.fixture
def repo(tmp_path):
    db = str(tmp_path / "test.db")
    ensure_schema(db)
    r = Repository(db)
    r.connect()
    return r


def _make_flac(path: Path, tags: dict | None = None) -> str:
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
    path.write_bytes(b"fLaC" + hdr + sinfo + last)
    from mutagen.flac import FLAC
    audio = FLAC(str(path))
    audio.add_tags()
    if tags:
        for k, v in tags.items():
            audio[k] = v
    audio.save()
    return str(path)


def test_scan_imports_new_file(repo, tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    fp = music / "track.flac"
    _make_flac(fp, {"title": "Test Song", "artist": "Test Artist", "album": "Test Album", "date": "2020"})
    scanner = LibraryScanner(repo)
    stats = scanner.scan_directory(str(music))
    assert stats["imported"] == 1
    assert stats["scanned"] == 1
    artists = repo.list_artists()
    assert len(artists) == 1
    assert artists[0].name == "Test Artist"
    albums = repo.list_albums(artist_id=artists[0].id)
    assert len(albums) == 1


def test_scan_matches_existing_track(repo, tmp_path):
    aid = repo.add_artist("Existing Artist")
    alid = repo.add_album(aid, "Existing Album", year=2020)
    tid = repo.add_track(alid, "Existing Track", track_number=1)
    music = tmp_path / "music"
    music.mkdir()
    fp = music / "track.flac"
    _make_flac(fp)
    repo.update_track_file(tid, str(fp), "FLAC")
    scanner = LibraryScanner(repo)
    stats = scanner.scan_directory(str(music))
    assert stats["matched"] == 1
    assert stats["imported"] == 0


def test_scan_skips_non_audio(repo, tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    (music / "notes.txt").write_text("hello")
    (music / "cover.jpg").write_bytes(b"image")
    scanner = LibraryScanner(repo)
    stats = scanner.scan_directory(str(music))
    assert stats["scanned"] == 0


def test_scan_nonexistent_directory(repo):
    scanner = LibraryScanner(repo)
    stats = scanner.scan_directory("/nonexistent/path/xyz")
    assert stats["scanned"] == 0
    assert stats["errors"] == 0


def test_scan_reuses_existing_artist(repo, tmp_path):
    repo.add_artist("Shared Artist")
    music = tmp_path / "music"
    music.mkdir()
    d1 = music / "album1"
    d1.mkdir()
    _make_flac(d1 / "track1.flac", {"title": "Song 1", "artist": "Shared Artist", "album": "Album 1", "date": "2020"})
    d2 = music / "album2"
    d2.mkdir()
    _make_flac(d2 / "track2.flac", {"title": "Song 2", "artist": "Shared Artist", "album": "Album 2", "date": "2021"})
    scanner = LibraryScanner(repo)
    stats = scanner.scan_directory(str(music))
    assert stats["imported"] == 2
    artists = repo.list_artists()
    assert len(artists) == 1


def test_scan_missing_tags_skipped(repo, tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    fp = music / "untagged.flac"
    _make_flac(fp, {})
    scanner = LibraryScanner(repo)
    stats = scanner.scan_directory(str(music))
    assert stats["scanned"] == 1
    assert "imported" in stats


def test_prune_marks_missing(repo, tmp_path):
    aid = repo.add_artist("Artist")
    alid = repo.add_album(aid, "Album")
    tid = repo.add_track(alid, "Track", track_number=1)
    fake_path = str(tmp_path / "nonexistent.flac")
    repo.update_track_file(tid, fake_path, "FLAC")
    scanner = LibraryScanner(repo)
    removed = scanner.prune_missing()
    assert removed == 1
    track = repo.list_tracks(alid)[0]
    assert track.download_status == "missing"
    assert track.file_path is None


def test_prune_keeps_existing(repo, tmp_path):
    aid = repo.add_artist("Artist")
    alid = repo.add_album(aid, "Album")
    tid = repo.add_track(alid, "Track", track_number=1)
    music = tmp_path / "music"
    music.mkdir()
    fp = music / "real.flac"
    fp.write_bytes(b"audio data")
    repo.update_track_file(tid, str(fp), "FLAC")
    scanner = LibraryScanner(repo)
    removed = scanner.prune_missing()
    assert removed == 0
    track = repo.list_tracks(alid)[0]
    assert track.download_status == "downloaded"


def test_import_with_albumartist_tag(repo, tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    fp = music / "track.flac"
    _make_flac(fp, {
        "title": "Song",
        "artist": "Feat. Artist",
        "albumartist": "Main Artist",
        "album": "The Album",
        "date": "2022",
    })
    scanner = LibraryScanner(repo)
    stats = scanner.scan_directory(str(music))
    assert stats["imported"] == 1
    artists = repo.list_artists()
    assert artists[0].name == "Main Artist"


def test_import_with_track_total_tag(repo, tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    fp = music / "track.flac"
    _make_flac(fp, {
        "title": "Song",
        "artist": "Artist",
        "album": "Album",
        "tracknumber": "3/10",
        "tracktotal": "10",
    })
    scanner = LibraryScanner(repo)
    stats = scanner.scan_directory(str(music))
    assert stats["imported"] == 1
    albums = repo.list_albums()
    assert albums[0].total_tracks == 10
