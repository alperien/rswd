from __future__ import annotations

from pathlib import Path

import pytest

from rswd.backends.streamrip_ import StreamripBackend
from rswd.config import ConfigData


def test_backend_init_with_configdata():
    cfg = ConfigData()
    backend = StreamripBackend(cfg)
    assert backend._config["download_path"] == cfg.core.download_path
    assert backend._config["codec"] == cfg.quality.codec


def test_backend_init_with_dict():
    backend = StreamripBackend({"download_path": "/test/path", "codec": "ALAC"})
    assert backend._config["download_path"] == "/test/path"
    assert backend._config["codec"] == "ALAC"


def test_backend_init_none():
    backend = StreamripBackend()
    assert backend._config == {}


def test_search_artist_delegates_to_searcher(httpx_mock):
    httpx_mock.add_response(
        json={"data": [{"id": 1, "name": "Radiohead", "type": "artist"}]},
        url="https://api.deezer.com/search/artist?q=Radiohead",
    )
    backend = StreamripBackend()
    results = backend.search("artist", "Radiohead")
    assert len(results) == 1
    assert results[0].service_id == "1"
    assert results[0].media_type == "artist"


def test_search_album_delegates_to_searcher(httpx_mock):
    httpx_mock.add_response(
        json={
            "data": [{
                "id": 123,
                "title": "OK Computer",
                "artist": {"id": 1, "name": "Radiohead"},
                "release_date": "1997",
                "nb_tracks": 12,
                "type": "album",
            }]
        },
        url="https://api.deezer.com/search/album?q=OK+Computer",
    )
    backend = StreamripBackend()
    results = backend.search("album", "OK Computer")
    assert len(results) == 1
    assert results[0].title == "OK Computer"
    assert results[0].year == 1997


def test_search_empty_when_api_fails(httpx_mock):
    httpx_mock.add_response(status_code=500)
    backend = StreamripBackend()
    results = backend.search("album", "Fail")
    assert results == []


def test_get_album_info_deezer(httpx_mock):
    httpx_mock.add_response(
        json={
            "id": 12345,
            "title": "Test Album",
            "artist": {"id": 1, "name": "Test Artist"},
            "release_date": "2020-01-15",
            "nb_tracks": 2,
            "label": "Test Label",
            "explicit_lyrics": False,
            "tracks": {
                "data": [
                    {"id": 1, "title": "Track 1", "artist": {"id": 1, "name": "Test Artist"}, "duration": 180},
                    {"id": 2, "title": "Track 2", "artist": {"id": 1, "name": "Test Artist"}, "duration": 200},
                ]
            },
        },
        url="https://api.deezer.com/album/12345",
    )
    backend = StreamripBackend()
    info = backend.get_album_info("deezer", "12345")
    assert info.title == "Test Album"
    assert info.artist == "Test Artist"
    assert info.year == 2020
    assert len(info.tracks) == 2
    assert info.tracks[0].title == "Track 1"
    assert info.tracks[1].track_number == 2


def test_get_album_info_not_implemented_for_unknown_service():
    backend = StreamripBackend()
    with pytest.raises(NotImplementedError):
        backend.get_album_info("unknown", "123")


def test_configdata_to_dict_handles_empty_services():
    cfg = ConfigData()
    d = StreamripBackend._configdata_to_dict(cfg)
    assert "services" in d
    assert d["services"]["deezer"]["arl"] == ""
    assert d["services"]["tidal"]["access_token"] == ""


def test_configdata_to_dict_with_services():
    cfg = ConfigData()
    cfg.services.deezer.arl = "test-arl"
    cfg.services.tidal.access_token = "test-token"
    d = StreamripBackend._configdata_to_dict(cfg)
    assert d["services"]["deezer"]["arl"] == "test-arl"
    assert d["services"]["tidal"]["access_token"] == "test-token"


def test_login_and_validate_returns_empty():
    backend = StreamripBackend()
    assert backend.login_and_validate() == {}
