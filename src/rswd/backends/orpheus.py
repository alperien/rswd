from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from rswd.backends.base import (
    AlbumInfo,
    DownloadResult,
    SearchDownloadBackend,
    SearchResult,
)

logger = logging.getLogger("rswd.backends.orpheus")


class OrpheusBackend(SearchDownloadBackend):
    def __init__(self, config: dict | None = None):
        self._config = config or {}

    def search(self, media_type: str, query: str, limit: int = 10) -> list[SearchResult]:
        logger.info("OrpheusDL search: %s '%s'", media_type, query)
        logger.warning("OrpheusDL search not yet implemented, returning empty results")
        return []

    def search_artist_discography(self, artist_name: str) -> dict[str, list[AlbumInfo]]:
        logger.info("OrpheusDL discography: '%s'", artist_name)
        return {}

    def get_album_info(self, service: str, service_id: str) -> AlbumInfo:
        raise NotImplementedError("OrpheusBackend.get_album_info not yet implemented")

    def download_album(
        self,
        service: str,
        service_id: str,
        album_info: AlbumInfo,
        output_dir: Path,
        quality: int = 2,
        codec: Optional[str] = None,
    ) -> list[DownloadResult]:
        raise NotImplementedError("OrpheusBackend.download_album not yet implemented")

    def login_and_validate(self) -> dict[str, bool]:
        raise NotImplementedError("OrpheusBackend.login_and_validate not yet implemented")
