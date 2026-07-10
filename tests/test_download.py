from __future__ import annotations

from pathlib import Path

import mutagen
import pytest

from rswd.config import ConfigData, CoreConfig, FilepathsConfig
from rswd.db.repository import Repository
from rswd.db.schema import ensure_schema
from rswd.download import DownloadPipeline


@pytest.fixture
def config(tmp_path):
    return ConfigData(
        core=CoreConfig(download_path=str(tmp_path / "music")),
        filepaths=FilepathsConfig(
            album_folder="{albumartist}/{album} ({year})",
            track_file="{tracknum:02d}. {artist} - {title}{ext}",
        ),
    )


@pytest.fixture
def repo(tmp_path):
    db = str(tmp_path / "test.db")
    ensure_schema(db)
    r = Repository(db)
    r.connect()
    yield r
    r.close()


@pytest.fixture
def pipeline(config, repo):
    return DownloadPipeline(config, repo)


def _make_test_flac(path: Path, title: str = "Test") -> str:
    import struct
    # Build a minimal valid FLAC STREAMINFO block (34 bytes)
    sinfo = struct.pack(">HH", 4096, 4096)                # min/max blocksize
    sinfo += struct.pack(">I", 0)[1:4]                    # min framesize = 0 (3 bytes)
    sinfo += struct.pack(">I", 0)[1:4]                    # max framesize = 0 (3 bytes)
    sinfo += struct.pack(">H", 44100 >> 4)                # sample rate upper 16 bits
    sinfo += struct.pack("B", 0x42)                       # low4_sample_rate + channels-1 + highbit_bps-1
    sinfo += struct.pack(">Q", 15 << 36)[3:8]             # low4_bps-1 (15) + total_samples (0)
    sinfo += b"\x00" * 16                                  # MD5 signature
    # Metadata block headers
    hdr_streaminfo = struct.pack("B", 0x00) + struct.pack(">I", 34)[1:4]
    hdr_padding = struct.pack("B", 0x81) + struct.pack(">I", 0)[1:4]
    path.write_bytes(b"fLaC" + hdr_streaminfo + sinfo + hdr_padding)
    from mutagen.flac import FLAC
    audio = FLAC(str(path))
    audio["title"] = title
    audio.save()
    return str(path)


class TestVerify:
    def test_verify_valid_file(self, tmp_path, pipeline):
        fp = _make_test_flac(tmp_path / "track.flac")
        assert pipeline.verify_file(Path(fp)) is True

    def test_verify_missing_file(self, tmp_path, pipeline):
        assert pipeline.verify_file(Path(str(tmp_path / "nonexistent.flac"))) is False

    def test_verify_empty_file(self, tmp_path, pipeline):
        f = tmp_path / "empty.flac"
        f.write_bytes(b"")
        assert pipeline.verify_file(f) is False


class TestChecksum:
    def test_checksum_consistent(self, tmp_path, pipeline):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello" * 1000)
        c1 = pipeline.compute_checksum(f)
        c2 = pipeline.compute_checksum(f)
        assert c1 == c2
        assert len(c1) == 64  # SHA256 hex

    def test_checksum_nonexistent_file(self, tmp_path, pipeline):
        f = tmp_path / "nonexistent.bin"
        assert pipeline.compute_checksum(f) is None


class TestMove:
    def test_move_to_library(self, tmp_path, pipeline):
        src = tmp_path / "source.flac"
        src.write_bytes(b"audio data")
        dest = pipeline.move_to_library(
            src,
            "TestArtist", "TestAlbum", 2020,
            1, "TestArtist", "Test Song",
            ".flac",
        )
        assert dest.exists()
        assert "TestArtist" in str(dest)
        assert "01." in dest.name
        assert not src.exists()


class TestProcessTrack:
    def test_process_track_success(self, tmp_path, pipeline, repo):
        src = tmp_path / "track.flac"
        _make_test_flac(src)
        aid = repo.add_artist("TestArtist")
        alid = repo.add_album(aid, "TestAlbum", year=2020)
        tid = repo.add_track(alid, "Test", track_number=1)
        result = pipeline.process_track(
            src, alid, tid,
            "TestArtist", "TestAlbum", 2020,
            1, "TestArtist", "Test",
            "deezer", quality=2,
        )
        assert result is not None
        assert result.exists()
        assert not src.exists()
        track = repo.list_tracks(alid)[0]
        assert track.download_status == "downloaded"
        assert track.file_path is not None
        assert "FLAC" in (track.file_format or "")
        stats = repo.library_stats()
        assert stats["downloaded"] >= 1
