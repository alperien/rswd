from __future__ import annotations

import pytest

from rswd.db.repository import Repository
from rswd.db.schema import ensure_schema


@pytest.fixture
def repo(tmp_path):
    db = str(tmp_path / "test.db")
    ensure_schema(db)
    r = Repository(db)
    r.connect()
    return r


def test_get_nonexistent_artist(repo):
    assert repo.get_artist(99999) is None


def test_get_nonexistent_album(repo):
    assert repo.get_album(99999) is None


def test_get_artist_by_name_nonexistent(repo):
    assert repo.get_artist_by_name("Nobody") is None


def test_get_track_by_path_nonexistent(repo):
    assert repo.get_track_by_path("/nonexistent") is None


def test_list_albums_empty(repo):
    assert repo.list_albums() == []


def test_list_tracks_empty(repo):
    assert repo.list_tracks(999) == []


def test_remove_nonexistent_artist(repo):
    assert repo.remove_artist(99999) is False


def test_set_monitored_nonexistent(repo):
    assert repo.set_monitored(99999, True) is False


def test_album_exists_no_year(repo):
    aid = repo.add_artist("Artist")
    repo.add_album(aid, "Album")
    assert repo.album_exists(aid, "Album") is True
    assert repo.album_exists(aid, "Album", 2020) is False


def test_multiple_albums_same_name_diff_artist(repo):
    aid1 = repo.add_artist("Artist 1")
    aid2 = repo.add_artist("Artist 2")
    repo.add_album(aid1, "Same Name")
    repo.add_album(aid2, "Same Name")
    assert len(repo.list_albums(artist_id=aid1)) == 1
    assert len(repo.list_albums(artist_id=aid2)) == 1


def test_list_albums_filter_by_status(repo):
    aid = repo.add_artist("Artist")
    repo.add_album(aid, "Album 1")
    repo.add_album(aid, "Album 2")
    albums = repo.list_albums(artist_id=aid, status="complete")
    assert len(albums) == 0


def test_update_album_status_nonexistent(repo):
    repo.update_album_status(99999, "complete")  # should not raise


def test_add_download_log_with_nulls(repo):
    aid = repo.add_artist("Artist")
    alid = repo.add_album(aid, "Album")
    tid = repo.add_track(alid, "Track")
    log_id = repo.add_download_log(tid, "deezer")
    assert log_id > 0


def test_update_track_file_with_missing_columns(repo):
    aid = repo.add_artist("Artist")
    alid = repo.add_album(aid, "Album")
    tid = repo.add_track(alid, "Track")
    repo.update_track_file(tid, "/path", "FLAC")
    track = repo.list_tracks(alid)[0]
    assert track.file_path == "/path"
    assert track.sample_rate is None


def test_library_stats_with_track_variants(repo):
    aid = repo.add_artist("Artist")
    alid = repo.add_album(aid, "Album")
    tid = repo.add_track(alid, "Track")
    repo.update_track_file(tid, "/path.flac", "FLAC")
    stats = repo.library_stats()
    assert stats["tracks"] == 1
    assert stats["downloaded"] == 1
