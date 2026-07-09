from __future__ import annotations

from pathlib import Path

import pytest

from rswd.metadata.replaygain import ReplayGainScanner


def _make_flac(path: Path, add_tags: bool = False) -> str:
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
    if add_tags:
        from mutagen.flac import FLAC
        audio = FLAC(str(path))
        audio.add_tags()
        audio.save()
    return str(path)


def test_parse_ebur128_output():
    scanner = ReplayGainScanner()
    output = """
    Integrated loudness:
      I:         -14.8 dBFS
      LRA:        10.0 dB
    Peak:
      Peak:       -2.3 dBFS
    """
    result = scanner._parse_ebur128_output(output)
    assert result["track_gain"] == -14.8
    assert result["track_peak"] == -2.3


def test_parse_ebur128_output_no_match():
    scanner = ReplayGainScanner()
    result = scanner._parse_ebur128_output("no data here")
    assert result["track_gain"] is None
    assert result["track_peak"] is None


def test_writes_track_gain_to_flac(tmp_path):
    fp = _make_flac(tmp_path / "track.flac", add_tags=True)
    scanner = ReplayGainScanner()
    assert scanner.write_track_gain(fp, -14.8, 0.5) is True
    import mutagen
    audio = mutagen.File(fp)
    assert audio is not None
    assert audio.tags.get("REPLAYGAIN_TRACK_GAIN") == ["-14.80 dB"]
    assert audio.tags.get("REPLAYGAIN_TRACK_PEAK") == ["0.500000"]


def test_writes_track_gain_to_file_without_tags(tmp_path):
    fp = _make_flac(tmp_path / "untagged.flac", add_tags=False)
    scanner = ReplayGainScanner()
    assert scanner.write_track_gain(fp, -10.0, 0.8) is True


def test_write_track_gain_nonexistent_file():
    scanner = ReplayGainScanner()
    assert scanner.write_track_gain("/nonexistent/file.flac", -10.0, 0.5) is False


def test_scan_file_missing_ffmpeg(tmp_path):
    fp = _make_flac(tmp_path / "track.flac")
    scanner = ReplayGainScanner(ffmpeg_path="ffmpeg_nonexistent")
    result = scanner.scan_file(fp)
    assert result is None


def test_scan_and_embed_missing_ffmpeg(tmp_path):
    fp = _make_flac(tmp_path / "track.flac", add_tags=True)
    scanner = ReplayGainScanner(ffmpeg_path="ffmpeg_nonexistent")
    assert scanner.scan_and_embed(fp) is False
