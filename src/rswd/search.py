from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger("rswd.search")

DEEZER_API = "https://api.deezer.com"


@dataclass(frozen=True)
class SearchHit:
    service: str
    service_id: str
    title: str
    artist: str
    album: str | None = None
    year: int | None = None
    track_count: int | None = None
    cover_url: str | None = None
    hit_type: str = "album"


class Searcher:
    def __init__(self, timeout: float = 15.0):
        self._client = httpx.Client(timeout=timeout)

    def __enter__(self) -> Searcher:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def search_album(self, query: str, service: str = "deezer") -> list[SearchHit]:
        if service != "deezer":
            logger.info("Service %r not yet implemented, falling back to Deezer", service)
        return self._search_deezer_album(query)

    def _search_deezer_album(self, query: str) -> list[SearchHit]:
        try:
            resp = self._client.get(f"{DEEZER_API}/search/album", params={"q": query})
            resp.raise_for_status()
            data = resp.json()
            hits: list[SearchHit] = []
            for item in data.get("data", [])[:15]:
                year = None
                release_date = item.get("release_date", "")
                if release_date and len(release_date) >= 4:
                    try:
                        year = int(release_date[:4])
                    except (ValueError, TypeError):
                        year = None
                hits.append(SearchHit(
                    service="deezer",
                    service_id=str(item.get("id", "")),
                    title=item.get("title", "Unknown"),
                    artist=item.get("artist", {}).get("name", "Unknown Artist"),
                    album=item.get("title", "Unknown"),
                    year=year,
                    track_count=item.get("nb_tracks"),
                    cover_url=item.get("cover_medium") or item.get("cover"),
                    hit_type="album",
                ))
            return hits
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Deezer search failed: %s", e)
            return []

    def search_artist(self, query: str, service: str = "deezer") -> list[SearchHit]:
        if service != "deezer":
            logger.info("Service %r not yet implemented, falling back to Deezer", service)
        return self._search_deezer_artist(query)

    def _search_deezer_artist(self, query: str) -> list[SearchHit]:
        try:
            resp = self._client.get(f"{DEEZER_API}/search/artist", params={"q": query})
            resp.raise_for_status()
            data = resp.json()
            hits: list[SearchHit] = []
            for item in data.get("data", [])[:10]:
                hits.append(SearchHit(
                    service="deezer",
                    service_id=str(item.get("id", "")),
                    title=item.get("name", "Unknown"),
                    artist=item.get("name", "Unknown Artist"),
                    cover_url=item.get("picture_medium") or item.get("picture"),
                    hit_type="artist",
                ))
            return hits
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Deezer artist search failed: %s", e)
            return []

    # TODO: not yet called by any code path; retained for future integration
    def get_artist_discography(self, artist_name: str) -> list[dict]:
        """Fetch all albums for an artist from Deezer by name."""
        try:
            artist_hits = self._search_deezer_artist(artist_name)
            if not artist_hits:
                return []
            deezer_id = artist_hits[0].service_id
            resp = self._client.get(
                f"{DEEZER_API}/artist/{deezer_id}/albums",
                params={"limit": 100},
            )
            resp.raise_for_status()
            data = resp.json()
            albums: list[dict] = []
            for item in data.get("data", []):
                year = None
                release_date = item.get("release_date", "")
                if release_date and len(release_date) >= 4:
                    try:
                        year = int(release_date[:4])
                    except (ValueError, TypeError):
                        year = None
                albums.append({
                    "title": item.get("title", "Unknown"),
                    "year": year,
                    "track_count": item.get("nb_tracks"),
                    "deezer_id": str(item.get("id", "")),
                    "type": item.get("record_type", "album"),
                })
            return albums
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Deezer discography lookup failed for %s: %s", artist_name, e)
            return []

    def close(self):
        self._client.close()
