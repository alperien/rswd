from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from streamrip import Config as RpConfig  # type: ignore[import-untyped]
from streamrip.config import BLANK_CONFIG_PATH  # type: ignore[import-untyped]

from rswd.backends.base import (
    AlbumInfo,
    DownloadResult,
    SearchDownloadBackend,
    SearchResult,
    TrackInfo,
)
from rswd.config import ConfigData
from rswd.search import Searcher

logger = logging.getLogger("rswd.backends.streamrip")


class StreamripBackend(SearchDownloadBackend):
    def __init__(self, config: ConfigData | dict | None = None):
        self._rp_config: RpConfig | None = None
        self._searcher: Searcher | None = None
        if isinstance(config, ConfigData):
            self._config = self._configdata_to_dict(config)
        else:
            self._config = config or {}

    @staticmethod
    def _configdata_to_dict(cfg: ConfigData) -> dict:
        return {
            "download_path": cfg.core.download_path,
            "codec": cfg.quality.codec,
            "concurrency": cfg.quality.concurrency,
            "services": {
                "deezer": {"arl": cfg.services.deezer.arl},
                "tidal": {
                    "access_token": cfg.services.tidal.access_token,
                    "refresh_token": cfg.services.tidal.refresh_token,
                    "user_id": cfg.services.tidal.user_id,
                    "country_code": cfg.services.tidal.country_code,
                },
                "qobuz": {
                    "email_or_userid": cfg.services.qobuz.email_or_userid,
                    "password_or_token": cfg.services.qobuz.password_or_token,
                    "app_id": cfg.services.qobuz.app_id,
                    "secrets": list(cfg.services.qobuz.secrets),
                },
                "soundcloud": {
                    "client_id": cfg.services.soundcloud.client_id,
                    "app_version": cfg.services.soundcloud.app_version,
                },
            },
        }

    def _build_rp_config(self, cfg: dict) -> RpConfig:
        rp = RpConfig(BLANK_CONFIG_PATH)
        rp.session.downloads.folder = cfg.get("download_path", "~/music")
        codec = cfg.get("codec")
        rp.session.conversion.enabled = bool(codec)
        rp.session.conversion.codec = (codec or "FLAC").upper()
        rp.session.downloads.concurrency = True
        rp.session.downloads.max_connections = cfg.get("concurrency", 3)
        services = cfg.get("services", {})
        if "deezer" in services:
            rp.session.deezer.arl = services["deezer"].get("arl", "")
        tidal = services.get("tidal", {})
        if tidal.get("access_token"):
            rp.session.tidal.access_token = tidal["access_token"]
            rp.session.tidal.refresh_token = tidal.get("refresh_token", "")
            rp.session.tidal.user_id = tidal.get("user_id", "")
            rp.session.tidal.country_code = tidal.get("country_code", "")
        qobuz = services.get("qobuz", {})
        if qobuz.get("email_or_userid"):
            rp.session.qobuz.email_or_userid = qobuz["email_or_userid"]
            rp.session.qobuz.password_or_token = qobuz.get("password_or_token", "")
            rp.session.qobuz.app_id = qobuz.get("app_id", "")
            rp.session.qobuz.secrets = qobuz.get("secrets", [])
        sc = services.get("soundcloud", {})
        if sc.get("client_id"):
            rp.session.soundcloud.client_id = sc["client_id"]
            rp.session.soundcloud.app_version = sc.get("app_version", "")
        return rp

    def _get_rp_config(self) -> RpConfig:
        if self._rp_config is None:
            self._rp_config = self._build_rp_config(self._config)
        return self._rp_config

    def _scan_output(self, output_dir: Path, album_info: AlbumInfo) -> list[DownloadResult]:
        results: list[DownloadResult] = []
        for track in album_info.tracks:
            candidates = list(output_dir.rglob(f"*{track.service_id}*"))
            if not candidates:
                candidates = list(output_dir.rglob(f"*{track.track_number:02d}*"))
            if not candidates:
                candidates = list(output_dir.glob(f"*.flac")) or list(output_dir.glob(f"*.mp3"))
            if candidates:
                results.append(DownloadResult(
                    track_info=track,
                    file_path=candidates[0],
                    success=True,
                ))
            else:
                results.append(DownloadResult(
                    track_info=track,
                    file_path=output_dir,
                    success=False,
                    error=f"File not found for track {track.track_number}",
                ))
        return results

    def search(self, media_type: str, query: str, limit: int = 10) -> list[SearchResult]:
        logger.info("Searching for %s: '%s'", media_type, query)
        if self._searcher is None:
            self._searcher = Searcher()
        if media_type == "artist":
            hits = self._searcher.search_artist(query)
        else:
            hits = self._searcher.search_album(query)
        results: list[SearchResult] = []
        for hit in hits[:limit]:
            results.append(SearchResult(
                service=hit.service,
                media_type=hit.hit_type,
                service_id=hit.service_id,
                title=hit.title,
                artists=(hit.artist,),
                year=hit.year,
                track_count=hit.track_count,
                cover_url=hit.cover_url,
            ))
        return results

    def search_artist_discography(self, artist_name: str) -> dict[str, list[AlbumInfo]]:
        logger.info("Fetching discography for '%s'", artist_name)
        if self._searcher is None:
            self._searcher = Searcher()
        hits = self._searcher.search_album(artist_name)
        albums: dict[str, list[AlbumInfo]] = {}
        for hit in hits:
            albums.setdefault("albums", [])
            if hit.track_count:
                albums["albums"].append(AlbumInfo(
                    service=hit.service,
                    service_id=hit.service_id,
                    title=hit.title,
                    artist=hit.artist,
                    year=hit.year,
                    total_tracks=hit.track_count,
                ))
        return albums

    def get_album_info(self, service: str, service_id: str) -> AlbumInfo:
        logger.info("Fetching album info for %s/%s", service, service_id)
        try:
            import httpx
            if service == "deezer":
                resp = httpx.get(f"https://api.deezer.com/album/{service_id}", timeout=10)
                resp.raise_for_status()
                data = resp.json()
                tracks = []
                for i, t in enumerate(data.get("tracks", {}).get("data", []), 1):
                    tracks.append(TrackInfo(
                        service="deezer",
                        service_id=str(t["id"]),
                        title=t["title"],
                        artist=t["artist"]["name"],
                        album=data["title"],
                        album_id=service_id,
                        track_number=i,
                        duration_s=t.get("duration"),
                    ))
                year = None
                release_date = data.get("release_date", "")
                if release_date and len(release_date) >= 4:
                    year = int(release_date[:4])
                return AlbumInfo(
                    service="deezer",
                    service_id=service_id,
                    title=data["title"],
                    artist=data["artist"]["name"],
                    year=year,
                    tracks=tuple(tracks),
                    cover_url=data.get("cover_medium") or data.get("cover"),
                    label=data.get("label"),
                    total_tracks=data.get("nb_tracks"),
                    explicit=data.get("explicit_lyrics", False),
                )
        except Exception as e:
            logger.warning("Failed to get album info for %s/%s: %s", service, service_id, e)
        raise NotImplementedError(f"get_album_info not implemented for {service}/{service_id}")

    def download_album(
        self,
        service: str,
        service_id: str,
        album_info: AlbumInfo,
        output_dir: Path,
        quality: int = 2,
        codec: Optional[str] = None,
    ) -> list[DownloadResult]:
        logger.info("Downloading %s/%s to %s (quality=%d)", service, service_id, output_dir, quality)

        async def _download():
            config = self._get_rp_config()
            config.session.downloads.folder = str(output_dir)
            from streamrip.rip.main import Main  # type: ignore[import-untyped]
            try:
                async with Main(config) as main:
                    await main.add_by_id(service, "album", service_id)
                    await main.resolve()
                    await main.rip()
            except Exception as e:
                logger.warning("streamrip download failed: %s", e)
            return self._scan_output(output_dir, album_info)

        return asyncio.run(_download())

    def login_and_validate(self) -> dict[str, bool]:
        return {}
