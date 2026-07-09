from __future__ import annotations

from rswd.backends.base import SearchResult, AlbumInfo, TrackInfo, DownloadResult


def test_search_result_defaults():
    r = SearchResult(service="deezer", media_type="album", service_id="1", title="Test", artists=("A",))
    assert r.year is None
    assert r.duration_s is None
    assert r.cover_url is None
    assert r.extra == {}


def test_search_result_frozen():
    r = SearchResult(service="deezer", media_type="album", service_id="1", title="Test", artists=("A",))
    import pytest
    with pytest.raises(Exception):
        r.title = "Changed"


def test_track_info_defaults():
    t = TrackInfo(service="deezer", service_id="1", title="T", artist="A", album="Al", album_id="1", track_number=1)
    assert t.disc_number == 1
    assert t.duration_s is None
    assert t.isrc is None
    assert t.explicit is False
    assert t.file_format is None


def test_album_info_empty_tracks():
    a = AlbumInfo(service="deezer", service_id="1", title="A", artist="Ar")
    assert a.tracks == ()
    assert a.cover_url is None
    assert a.total_tracks is None


def test_download_result_success():
    from pathlib import Path
    r = DownloadResult(track_info=None, file_path=Path("/test"), success=True)
    assert r.success is True
    assert r.error is None


def test_download_result_failure():
    from pathlib import Path
    r = DownloadResult(track_info=None, file_path=Path("/test"), success=False, error="Something went wrong")
    assert r.success is False
    assert r.error == "Something went wrong"
