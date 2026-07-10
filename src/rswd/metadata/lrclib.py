from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger("rswd.metadata.lrclib")


@dataclass
class LyricsResult:
    source: str
    plain: Optional[str] = None
    synced: Optional[str] = None
    is_instrumental: bool = False


class LRCLibProvider:
    BASE_URL = "https://lrclib.net/api"

    def __init__(self, timeout: float = 10.0):
        self._client = httpx.Client(timeout=timeout)

    def fetch(
        self,
        track: str,
        artist: str,
        album: str | None = None,
        duration: int | None = None,
    ) -> LyricsResult | None:
        params = {"track_name": track, "artist_name": artist}
        if album:
            params["album_name"] = album
        if duration is not None:
            params["duration"] = str(duration)

        try:
            resp = self._client.get(f"{self.BASE_URL}/get", params=params)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return LyricsResult(
                source="lrclib",
                plain=data.get("plainLyrics"),
                synced=data.get("syncedLyrics"),
                is_instrumental=data.get("isInstrumental", False),
            )
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("LRCLIB request failed for '%s' by %s: %s", track, artist, e)
            return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self._client.close()
