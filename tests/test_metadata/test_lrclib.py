from __future__ import annotations

import pytest
import httpx

from rswd.metadata.lrclib import LRCLibProvider, LyricsResult


def test_fetch_returns_none_on_404(httpx_mock):
    httpx_mock.add_response(status_code=404)
    with LRCLibProvider() as provider:
        result = provider.fetch("Nonexistent", "Nobody")
        assert result is None


def test_fetch_returns_lyrics(httpx_mock):
    httpx_mock.add_response(
        json={
            "id": 12345,
            "trackName": "Paranoid Android",
            "artistName": "Radiohead",
            "albumName": "OK Computer",
            "duration": 383,
            "plainLyrics": "Please could you stop the noise...\n",
            "syncedLyrics": "[00:12.00]Please could you stop the noise...\n",
            "isInstrumental": False,
        }
    )
    with LRCLibProvider() as provider:
        result = provider.fetch("Paranoid Android", "Radiohead")
        assert result is not None
        assert result.source == "lrclib"
        assert "Please could you stop" in (result.plain or "")
        assert "[00:12.00]" in (result.synced or "")
        assert result.is_instrumental is False


def test_fetch_instrumental(httpx_mock):
    httpx_mock.add_response(
        json={
            "id": 999,
            "trackName": "Track 1",
            "artistName": "Artist",
            "plainLyrics": None,
            "syncedLyrics": None,
            "isInstrumental": True,
        }
    )
    with LRCLibProvider() as provider:
        result = provider.fetch("Track 1", "Artist")
        assert result is not None
        assert result.is_instrumental is True
        assert result.plain is None


def test_fetch_with_album_and_duration(httpx_mock):
    httpx_mock.add_response(
        json={
            "id": 1,
            "trackName": "Song",
            "artistName": "Singer",
            "albumName": "Album",
            "duration": 200,
            "plainLyrics": "la la la",
            "syncedLyrics": None,
            "isInstrumental": False,
        }
    )
    with LRCLibProvider() as provider:
        result = provider.fetch("Song", "Singer", album="Album", duration=200)
        assert result is not None
        assert result.plain == "la la la"


def test_http_error_returns_none(httpx_mock):
    httpx_mock.add_response(status_code=503)
    with LRCLibProvider() as provider:
        result = provider.fetch("Any", "One")
        assert result is None
