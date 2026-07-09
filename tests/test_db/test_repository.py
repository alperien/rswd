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


class TestArtists:
    def test_add_and_get(self, repo):
        aid = repo.add_artist("Radiohead", is_monitored=True, monitor_quality=2)
        artist = repo.get_artist(aid)
        assert artist.name == "Radiohead"
        assert artist.is_monitored is True
        assert artist.monitor_quality == 2

    def test_add_duplicate_name_allowed(self, repo):
        aid1 = repo.add_artist("Radiohead")
        aid2 = repo.add_artist("Radiohead")
        assert aid1 != aid2  # no unique constraint on name alone

    def test_list_artists(self, repo):
        repo.add_artist("Alpha")
        repo.add_artist("Beta", is_monitored=True)
        repo.add_artist("Gamma")
        all_artists = repo.list_artists()
        assert len(all_artists) >= 3
        monitored = repo.list_artists(monitored_only=True)
        assert len(monitored) == 1
        assert monitored[0].name == "Beta"

    def test_remove_cascade(self, repo):
        aid = repo.add_artist("TestArtist")
        alid = repo.add_album(aid, "TestAlbum", year=2020)
        repo.add_track(alid, "Track 1", track_number=1)
        repo.remove_artist(aid)
        assert repo.get_artist(aid) is None
        assert repo.get_album(alid) is None

    def test_set_monitored(self, repo):
        aid = repo.add_artist("Test")
        repo.set_monitored(aid, True)
        assert repo.get_artist(aid).is_monitored is True
        repo.set_monitored(aid, False)
        assert repo.get_artist(aid).is_monitored is False


class TestAlbums:
    def test_add_and_list(self, repo):
        aid = repo.add_artist("Artist")
        alid1 = repo.add_album(aid, "Album 1", year=2000)
        alid2 = repo.add_album(aid, "Album 2", year=2005)
        albums = repo.list_albums(artist_id=aid)
        assert len(albums) == 2
        assert albums[0].year == 2005  # DESC order

    def test_album_exists(self, repo):
        aid = repo.add_artist("Artist")
        repo.add_album(aid, "Unique", year=2020)
        assert repo.album_exists(aid, "Unique", 2020) is True
        assert repo.album_exists(aid, "Nonexistent", 2020) is False

    def test_update_status(self, repo):
        aid = repo.add_artist("Artist")
        alid = repo.add_album(aid, "Album")
        repo.update_album_status(alid, "complete", quality_tier=2)
        album = repo.get_album(alid)
        assert album.download_status == "complete"
        assert album.quality_tier == 2


class TestTracks:
    def test_add_and_list(self, repo):
        aid = repo.add_artist("Artist")
        alid = repo.add_album(aid, "Album")
        repo.add_track(alid, "Track 1", track_number=1, duration=180.0)
        repo.add_track(alid, "Track 2", track_number=2, duration=200.0)
        tracks = repo.list_tracks(alid)
        assert len(tracks) == 2
        assert tracks[0].track_number == 1

    def test_update_file_info(self, repo):
        aid = repo.add_artist("Artist")
        alid = repo.add_album(aid, "Album")
        tid = repo.add_track(alid, "Track", track_number=1)
        repo.update_track_file(tid, "/path/to/file.flac", "FLAC", bitrate=1411, sample_rate=44100, bit_depth=16)
        track = repo.list_tracks(alid)[0]
        assert track.file_path == "/path/to/file.flac"
        assert track.file_format == "FLAC"
        assert track.download_status == "downloaded"


class TestDownloadLog:
    def test_add_entry(self, repo):
        aid = repo.add_artist("Artist")
        alid = repo.add_album(aid, "Album")
        tid = repo.add_track(alid, "Track")
        log_id = repo.add_download_log(tid, "deezer", quality=2, file_path="/path/to/file.flac", file_size=12345, checksum="abc123")
        assert log_id > 0


class TestLibraryStats:
    def test_stats(self, repo):
        stats = repo.library_stats()
        assert "artists" in stats
        assert "albums" in stats
        assert "tracks" in stats
        assert "downloaded" in stats
