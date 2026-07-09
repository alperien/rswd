from __future__ import annotations

import pytest
import httpx

from rswd.search import Searcher


def test_search_album_deezer(httpx_mock):
    httpx_mock.add_response(
        json={
            "data": [
                {
                    "id": 12345,
                    "title": "OK Computer",
                    "artist": {"id": 1, "name": "Radiohead"},
                    "release_date": "1997-05-21",
                    "nb_tracks": 12,
                    "cover_medium": "https://example.com/cover.jpg",
                    "type": "album",
                }
            ]
        },
        url="https://api.deezer.com/search/album?q=OK+Computer",
    )
    searcher = Searcher()
    try:
        results = searcher.search_album("OK Computer")
        assert len(results) == 1
        assert results[0].title == "OK Computer"
        assert results[0].artist == "Radiohead"
        assert results[0].year == 1997
        assert results[0].track_count == 12
        assert results[0].service == "deezer"
        assert results[0].service_id == "12345"
    finally:
        searcher.close()


def test_search_album_empty(httpx_mock):
    httpx_mock.add_response(json={"data": []})
    searcher = Searcher()
    try:
        results = searcher.search_album("NonexistentAlbumXYZ")
        assert results == []
    finally:
        searcher.close()


def test_search_album_http_error(httpx_mock):
    httpx_mock.add_response(status_code=503)
    searcher = Searcher()
    try:
        results = searcher.search_album("Fail")
        assert results == []
    finally:
        searcher.close()


def test_search_artist_deezer(httpx_mock):
    httpx_mock.add_response(
        json={
            "data": [
                {
                    "id": 1,
                    "name": "Radiohead",
                    "picture_medium": "https://example.com/pic.jpg",
                    "type": "artist",
                }
            ]
        },
        url="https://api.deezer.com/search/artist?q=Radiohead",
    )
    searcher = Searcher()
    try:
        results = searcher.search_artist("Radiohead")
        assert len(results) == 1
        assert results[0].title == "Radiohead"
        assert results[0].service_id == "1"
        assert results[0].hit_type == "artist"
    finally:
        searcher.close()


def test_search_artist_empty(httpx_mock):
    httpx_mock.add_response(json={"data": []})
    searcher = Searcher()
    try:
        results = searcher.search_artist("Nobody")
        assert results == []
    finally:
        searcher.close()


def test_search_artist_http_error(httpx_mock):
    httpx_mock.add_response(status_code=500)
    searcher = Searcher()
    try:
        results = searcher.search_artist("Fail")
        assert results == []
    finally:
        searcher.close()


def test_search_album_without_release_date(httpx_mock):
    httpx_mock.add_response(
        json={
            "data": [
                {
                    "id": 999,
                    "title": "No Date Album",
                    "artist": {"id": 2, "name": "Artist"},
                    "release_date": "",
                    "nb_tracks": None,
                    "type": "album",
                }
            ]
        },
    )
    searcher = Searcher()
    try:
        results = searcher.search_album("No Date")
        assert len(results) == 1
        assert results[0].year is None
        assert results[0].track_count is None
    finally:
        searcher.close()


def test_search_album_fallback_to_deezer_for_tidal(httpx_mock):
    httpx_mock.add_response(
        json={
            "data": [
                {
                    "id": 123,
                    "title": "Album",
                    "artist": {"id": 1, "name": "Artist"},
                    "release_date": "2020",
                    "nb_tracks": 10,
                    "type": "album",
                }
            ]
        },
    )
    searcher = Searcher()
    try:
        results = searcher.search_album("Album", service="tidal")
        assert len(results) == 1
        assert results[0].service == "deezer"
    finally:
        searcher.close()


def test_search_album_unknown_service(httpx_mock):
    httpx_mock.add_response(
        json={
            "data": [
                {
                    "id": 456,
                    "title": "Some Album",
                    "artist": {"id": 3, "name": "Some Artist"},
                    "release_date": "2022",
                    "nb_tracks": 8,
                    "type": "album",
                }
            ]
        },
    )
    searcher = Searcher()
    try:
        results = searcher.search_album("Some Album", service="unknown")
        assert len(results) == 1
        assert results[0].service == "deezer"
    finally:
        searcher.close()


def test_search_no_results_truncated(httpx_mock):
    httpx_mock.add_response(json={"data": [{"id": i, "title": f"Album {i}", "artist": {"id": 1, "name": "A"}} for i in range(20)]})
    searcher = Searcher()
    try:
        results = searcher.search_album("A")
        assert len(results) <= 15
    finally:
        searcher.close()


def test_close_is_idempotent():
    searcher = Searcher()
    searcher.close()
    searcher.close()
