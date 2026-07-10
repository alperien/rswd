from __future__ import annotations

from pathlib import Path

import mutagen

from rswd.metadata.lyrics import LyricsEnricher
from rswd.metadata.lrclib import LyricsResult


def _make_flac(path: Path) -> str:
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
    audio.save()
    return str(path)


def test_embed_plain_lyrics(tmp_path):
    fp = _make_flac(tmp_path / "test.flac")
    with LyricsEnricher(prefer_synced=False) as enricher:
        result = LyricsResult(source="lrclib", plain="Hello world", synced=None)
        assert enricher._embed_in_file(fp, result) is True
    audio = mutagen.File(fp)
    assert audio is not None
    assert audio.tags.get("LYRICS") == ["Hello world"]


def test_embed_synced_lyrics(tmp_path):
    fp = _make_flac(tmp_path / "test.flac")
    with LyricsEnricher(prefer_synced=True) as enricher:
        result = LyricsResult(
            source="lrclib",
            plain="Hello world",
            synced="[00:01.00]Hello world",
        )
        assert enricher._embed_in_file(fp, result) is True
    audio = mutagen.File(fp)
    assert audio is not None
    assert audio.tags.get("LYRICS") == ["[00:01.00]Hello world"]


def test_embed_no_lyrics(tmp_path):
    fp = _make_flac(tmp_path / "test.flac")
    with LyricsEnricher() as enricher:
        result = LyricsResult(source="lrclib", plain=None, synced=None)
        assert enricher._embed_in_file(fp, result) is False


def test_embed_nonexistent_file(tmp_path):
    with LyricsEnricher() as enricher:
        result = LyricsResult(source="lrclib", plain="test")
        assert enricher._embed_in_file(str(tmp_path / "nope.flac"), result) is False


def test_fetch_and_embed_real_request(httpx_mock, tmp_path):
    fp = _make_flac(tmp_path / "test.flac")
    httpx_mock.add_response(
        json={"plainLyrics": "hello", "syncedLyrics": "[00:01]hello", "isInstrumental": False}
    )
    with LyricsEnricher(prefer_synced=True) as enricher:
        result = enricher.fetch_and_embed(fp, "Test", "Artist", "Album")
        assert result is True
    audio = mutagen.File(fp)
    assert audio is not None
    lyrics_tag = audio.tags.get("LYRICS")
    assert lyrics_tag is not None
    assert "hello" in str(lyrics_tag)


def test_embed_synced_lyrics_over_plain(tmp_path):
    fp = _make_flac(tmp_path / "test.flac")
    with LyricsEnricher(prefer_synced=True) as enricher:
        result = LyricsResult(
            source="lrclib",
            plain="plain text",
            synced="[00:01.00]synced text",
        )
        assert enricher._embed_in_file(fp, result) is True
    audio = mutagen.File(fp)
    assert audio is not None
    assert "[00:01" in str(audio.tags.get("LYRICS"))


def test_embed_plain_lyrics_prefer_plain_over_synced(tmp_path):
    fp = _make_flac(tmp_path / "test.flac")
    with LyricsEnricher(prefer_synced=False) as enricher:
        result = LyricsResult(
            source="lrclib",
            plain="plain version",
            synced="[00:01]synced version",
        )
        assert enricher._embed_in_file(fp, result) is True
    audio = mutagen.File(fp)
    assert audio is not None
    assert audio.tags.get("LYRICS") == ["plain version"]


def test_embed_returns_false_on_exception(tmp_path):
    with LyricsEnricher() as enricher:
        result = LyricsResult(source="lrclib", plain="test")
        assert enricher._embed_in_file(str(tmp_path / "nonexistent.dir" / "file.flac"), result) is False


