from __future__ import annotations

import logging
import time
from typing import Optional

try:
    import musicbrainzngs  # type: ignore[import-untyped]
except ImportError:
    musicbrainzngs = None  # type: ignore[assignment]

from rswd.config import SERVICE_NAME
from rswd.db.repository import Repository

logger = logging.getLogger("rswd.metadata.musicbrainz")


class MusicBrainzEnricher:
    def __init__(self, rate_limit: float = 1.0):
        if musicbrainzngs is not None:
            musicbrainzngs.set_useragent(
                SERVICE_NAME,
                "0.1.0",
                contact="user@example.com",
            )
            musicbrainzngs.set_rate_limit(rate_limit or 1.0)
        self._rate_limit = rate_limit

    def _available(self) -> bool:
        return musicbrainzngs is not None

    def enrich_artist(self, artist_name: str) -> Optional[dict]:
        if not self._available():
            logger.warning("musicbrainzngs not installed, skipping")
            return None
        try:
            result = musicbrainzngs.search_artists(artist=artist_name, limit=1)
            if result.get("artist-list"):
                return result["artist-list"][0]
            return None
        except Exception as e:
            logger.warning("MusicBrainz artist search failed for '%s': %s", artist_name, e)
            return None

    def enrich_album(self, album_title: str, artist_name: str | None = None) -> Optional[dict]:
        if not self._available():
            logger.warning("musicbrainzngs not installed, skipping")
            return None
        try:
            kwargs = {"release": album_title, "limit": 1}
            if artist_name:
                kwargs["artist"] = artist_name
            result = musicbrainzngs.search_releases(**kwargs)
            if result.get("release-list"):
                return result["release-list"][0]
            return None
        except Exception as e:
            logger.warning("MusicBrainz release search failed for '%s': %s", album_title, e)
            return None

    def enrich_track(self, recording: str, artist: str | None = None) -> Optional[dict]:
        if not self._available():
            logger.warning("musicbrainzngs not installed, skipping")
            return None
        try:
            kwargs = {"recording": recording, "limit": 1}
            if artist:
                kwargs["artist"] = artist
            result = musicbrainzngs.search_recordings(**kwargs)
            if result.get("recording-list"):
                return result["recording-list"][0]
            return None
        except Exception as e:
            logger.warning("MusicBrainz recording search failed for '%s': %s", recording, e)
            return None

    def enrich_artist_in_db(self, repo: Repository, artist_id: int) -> bool:
        artist = repo.get_artist(artist_id)
        if not artist or artist.mb_artistid:
            return False
        mb_data = self.enrich_artist(artist.name)
        if mb_data is None:
            return False
        mbid = mb_data.get("id")
        sort_name = mb_data.get("sort-name")
        if mbid:
            conn = repo.connect()
            conn.execute(
                "UPDATE artists SET mb_artistid = ?, sort_name = ? WHERE id = ?",
                (mbid, sort_name, artist_id),
            )
            conn.commit()
            logger.info("Enriched artist %d with MBID %s", artist_id, mbid)
            return True
        return False

    def enrich_album_in_db(self, repo: Repository, album_id: int) -> bool:
        album = repo.get_album(album_id)
        if not album or album.mb_albumid:
            return False
        artist = repo.get_artist(album.artist_id)
        artist_name = artist.name if artist else None
        mb_data = self.enrich_album(album.title, artist_name)
        if mb_data is None:
            return False
        mbid = mb_data.get("id")
        rgid = None
        release_group = mb_data.get("release-group", {})
        if release_group:
            rgid = release_group.get("id")
        if mbid:
            conn = repo.connect()
            conn.execute(
                "UPDATE albums SET mb_albumid = ?, mb_release_groupid = ? WHERE id = ?",
                (mbid, rgid, album_id),
            )
            conn.commit()
            logger.info("Enriched album %d with MBID %s", album_id, mbid)
            return True
        return False
