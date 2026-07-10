from __future__ import annotations

import asyncio
import concurrent.futures
import copy
import logging
import re
from pathlib import Path
from typing import Optional

import httpx
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
        try:
            rp = RpConfig(BLANK_CONFIG_PATH)
        except FileNotFoundError:
            logger.error("Streamrip config file not found: %s", BLANK_CONFIG_PATH)
            raise
        rp.session.downloads.folder = cfg.get("download_path", "~/music")
        codec = cfg.get("codec")
        rp.session.conversion.enabled = bool(codec)
        rp.session.conversion.codec = (codec or "FLAC").upper()
        rp.session.downloads.concurrency = True
        rp.session.downloads.max_connections = cfg.get("concurrency", 3)
        rp.session.database.downloads_enabled = False
        rp.session.database.failed_downloads_enabled = False
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
            file_path = None
            service_id_re = re.compile(
                r'(?:^|[^0-9])' + re.escape(track.service_id) + r'(?:[^0-9]|$)'
            )
            for f in output_dir.rglob("*"):
                if f.is_file() and service_id_re.search(f.name):
                    file_path = f
                    break
            if file_path is None:
                for ext in [".flac", ".mp3", ".ogg", ".m4a", ".opus", ".wav"]:
                    candidates = list(output_dir.rglob(f"*{track.track_number:02d}*{ext}"))
                    if candidates:
                        file_path = candidates[0]
                        break
            if file_path is not None:
                results.append(DownloadResult(
                    track_info=track,
                    file_path=file_path,
                    success=True,
                ))
            else:
                results.append(DownloadResult(
                    track_info=track,
                    file_path=None,
                    success=False,
                    error=f"File not found for track {track.track_number}",
                ))
        return results

    def search(self, media_type: str, query: str, limit: int = 10) -> list[SearchResult]:
        logger.info("Searching for %s: '%s'", media_type, query)
        if self._searcher is None:
            self._searcher = Searcher()
        try:
            if media_type == "artist":
                hits = self._searcher.search_artist(query)
            else:
                hits = self._searcher.search_album(query)
        except Exception as e:
            logger.error("Search failed for %s '%s': %s", media_type, query, e)
            raise
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
        artist_results = self._searcher.search_artist(artist_name)
        if artist_results:
            artist_hit = artist_results[0]
            hits = self._searcher.search_album(artist_hit.artist)
            matched_name = artist_hit.artist.lower()
            hits = [h for h in hits if h.artist.lower() == matched_name]
        else:
            hits = self._searcher.search_album(artist_name)
        albums: list[AlbumInfo] = []
        for hit in hits:
            if hit.track_count is not None:
                albums.append(AlbumInfo(
                    service=hit.service,
                    service_id=hit.service_id,
                    title=hit.title,
                    artist=hit.artist,
                    year=hit.year,
                    total_tracks=hit.track_count,
                ))
        return {"albums": albums}

    def get_album_info(self, service: str, service_id: str) -> AlbumInfo:
        logger.info("Fetching album info for %s/%s", service, service_id)
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
                    track_number=t.get("track_position", i),
                    duration_s=t.get("duration"),
                ))
            year = None
            release_date = data.get("release_date", "")
            if release_date and len(release_date) >= 4:
                try:
                    year = int(release_date[:4])
                except ValueError:
                    logger.warning("Invalid release date format: %s", release_date)
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
        raise NotImplementedError(f"get_album_info not implemented for service {service!r}")

    def download_album(
        self,
        service: str,
        service_id: str,
        album_info: AlbumInfo,
        output_dir: Path,
        quality: int = 2,
        codec: Optional[str] = None,
    ) -> list[DownloadResult]:
        # TODO: download_album blocks the thread; consider async refactor
        logger.info("Downloading %s/%s to %s (quality=%d)", service, service_id, output_dir, quality)

        async def _download():
            config = copy.deepcopy(self._get_rp_config())
            config.session.downloads.folder = str(output_dir)
            from streamrip.rip.main import Main  # type: ignore[import-untyped]
            try:
                async with Main(config) as main:
                    await main.add_by_id(service, "album", service_id)
                    await main.resolve()
                    await main.rip()
            except Exception as e:
                if isinstance(e, EOFError) or (isinstance(e, AssertionError) and not e.args):
                    logger.error("Download failed: Deezer ARL is missing or invalid. Set RSWD_DEEZER_ARL env var or configure via web UI at /config.")
                else:
                    logger.exception("streamrip download failed: %s", e)
                raise
            return self._scan_output(output_dir, album_info)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as pool:
                results = pool.submit(asyncio.run, _download()).result(timeout=300)
        else:
            results = asyncio.run(_download())
        return results

    def login_and_validate(self) -> dict[str, bool]:
        return {}
