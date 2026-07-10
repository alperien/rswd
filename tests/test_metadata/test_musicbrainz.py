from __future__ import annotations

from unittest.mock import patch

import musicbrainzngs
import pytest

from rswd.db.repository import Repository
from rswd.db.schema import ensure_schema
from rswd.metadata.musicbrainz_ import MusicBrainzEnricher


@pytest.fixture
def repo(tmp_path):
    db = str(tmp_path / "test.db")
    ensure_schema(db)
    r = Repository(db)
    r.connect()
    yield r
    r.close()


def test_enrich_artist_new_mbid(repo):
    aid = repo.add_artist("Test Artist")
    enricher = MusicBrainzEnricher(rate_limit=0)
    with patch("musicbrainzngs.search_artists") as mock_search:
        mock_search.return_value = {
            "artist-list": [
                {"id": "mbid-123", "sort-name": "Test Artist", "name": "Test Artist"}
            ]
        }
        assert enricher.enrich_artist_in_db(repo, aid) is True
    artist = repo.get_artist(aid)
    assert artist.mb_artistid == "mbid-123"
    assert artist.sort_name == "Test Artist"


def test_enrich_artist_skip_if_already_has_mbid(repo):
    aid = repo.add_artist("Test Artist", mb_artistid="existing-mbid")
    enricher = MusicBrainzEnricher(rate_limit=0)
    with patch("musicbrainzngs.search_artists") as mock_search:
        assert enricher.enrich_artist_in_db(repo, aid) is False
        mock_search.assert_not_called()


def test_enrich_artist_not_found(repo):
    aid = repo.add_artist("Unknown Artist XYZ")
    enricher = MusicBrainzEnricher(rate_limit=0)
    with patch("musicbrainzngs.search_artists") as mock_search:
        mock_search.return_value = {"artist-list": []}
        assert enricher.enrich_artist_in_db(repo, aid) is False


def test_enrich_artist_search_fails(repo):
    aid = repo.add_artist("Failing Artist")
    enricher = MusicBrainzEnricher(rate_limit=0)
    with patch("musicbrainzngs.search_artists") as mock_search:
        mock_search.side_effect = musicbrainzngs.MusicBrainzError("API error")
        assert enricher.enrich_artist_in_db(repo, aid) is False


def test_enrich_album_new_mbid(repo):
    aid = repo.add_artist("Test Artist")
    alid = repo.add_album(aid, "Test Album", year=2020)
    enricher = MusicBrainzEnricher(rate_limit=0)
    with patch("musicbrainzngs.search_releases") as mock_search:
        mock_search.return_value = {
            "release-list": [
                {
                    "id": "release-mbid",
                    "release-group": {"id": "rgid-123"},
                    "title": "Test Album",
                }
            ]
        }
        assert enricher.enrich_album_in_db(repo, alid) is True
    album = repo.get_album(alid)
    assert album.mb_albumid == "release-mbid"
    assert album.mb_release_groupid == "rgid-123"


def test_enrich_album_skip_if_already_has_mbid(repo):
    aid = repo.add_artist("Test Artist")
    alid = repo.add_album(aid, "Test Album", mb_albumid="existing-mbid")
    enricher = MusicBrainzEnricher(rate_limit=0)
    with patch("musicbrainzngs.search_releases") as mock_search:
        assert enricher.enrich_album_in_db(repo, alid) is False
        mock_search.assert_not_called()


def test_enrich_album_not_found(repo):
    aid = repo.add_artist("Test Artist")
    alid = repo.add_album(aid, "Unknown Album")
    enricher = MusicBrainzEnricher(rate_limit=0)
    with patch("musicbrainzngs.search_releases") as mock_search:
        mock_search.return_value = {"release-list": []}
        assert enricher.enrich_album_in_db(repo, alid) is False


def test_enrich_track_returns_data():
    enricher = MusicBrainzEnricher(rate_limit=0)
    with patch("musicbrainzngs.search_recordings") as mock_search:
        mock_search.return_value = {
            "recording-list": [
                {"id": "recording-mbid", "title": "Test Track"}
            ]
        }
        result = enricher.enrich_track("Test Track", "Test Artist")
        assert result is not None
        assert result["id"] == "recording-mbid"


def test_enrich_track_not_found():
    enricher = MusicBrainzEnricher(rate_limit=0)
    with patch("musicbrainzngs.search_recordings") as mock_search:
        mock_search.return_value = {"recording-list": []}
        result = enricher.enrich_track("Nonexistent")
        assert result is None


def test_enrich_album_without_release_group(repo):
    aid = repo.add_artist("Test Artist")
    alid = repo.add_album(aid, "Test Album")
    enricher = MusicBrainzEnricher(rate_limit=0)
    with patch("musicbrainzngs.search_releases") as mock_search:
        mock_search.return_value = {
            "release-list": [
                {"id": "release-mbid", "title": "Test Album"}
            ]
        }
        assert enricher.enrich_album_in_db(repo, alid) is True
    album = repo.get_album(alid)
    assert album.mb_albumid == "release-mbid"
    assert album.mb_release_groupid is None
