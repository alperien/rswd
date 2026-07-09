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

    def search_album(self, query: str, service: str = "deezer") -> list[SearchHit]:
        if service == "deezer":
            return self._search_deezer_album(query)
        elif service == "tidal":
            logger.info("Tidal search not yet implemented, falling back to Deezer")
            return self._search_deezer_album(query)
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
                    year = int(release_date[:4])
                hits.append(SearchHit(
                    service="deezer",
                    service_id=str(item["id"]),
                    title=item["title"],
                    artist=item["artist"]["name"],
                    album=item["title"],
                    year=year,
                    track_count=item.get("nb_tracks"),
                    cover_url=item.get("cover_medium") or item.get("cover"),
                    hit_type="album",
                ))
            return hits
        except httpx.HTTPError as e:
            logger.warning("Deezer search failed: %s", e)
            return []

    def search_artist(self, query: str, service: str = "deezer") -> list[SearchHit]:
        if service == "deezer":
            return self._search_deezer_artist(query)
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
                    service_id=str(item["id"]),
                    title=item["name"],
                    artist=item["name"],
                    cover_url=item.get("picture_medium") or item.get("picture"),
                    hit_type="artist",
                ))
            return hits
        except httpx.HTTPError as e:
            logger.warning("Deezer artist search failed: %s", e)
            return []

    def close(self):
        self._client.close()
