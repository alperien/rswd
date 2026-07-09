from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Optional

import mutagen

from rswd.config import ConfigData
from rswd.db.repository import Repository
from rswd.util import sanitize_filename, validate_path_length

logger = logging.getLogger("rswd.download")


class DownloadPipeline:
    def __init__(self, config: ConfigData, repo: Repository):
        self.config = config
        self.repo = repo

    def verify_file(self, file_path: Path) -> bool:
        if not file_path.is_file():
            logger.error("File not found: %s", file_path)
            return False
        if file_path.stat().st_size == 0:
            logger.error("File is empty: %s", file_path)
            return False
        try:
            audio = mutagen.File(str(file_path))
            if audio is None:
                logger.warning("Could not open audio file: %s", file_path)
                return False
            return True
        except mutagen.MutagenError as e:
            logger.error("Invalid audio file %s: %s", file_path, e)
            return False

    def compute_checksum(self, file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def move_to_library(
        self,
        source: Path,
        album_artist: str,
        album_title: str,
        year: int | None,
        track_num: int | None,
        track_artist: str,
        track_title: str,
        ext: str,
    ) -> Path:
        album_folder = self.config.filepaths.album_folder.format(
            albumartist=sanitize_filename(album_artist),
            album=sanitize_filename(album_title),
            year=year or "",
        )
        track_file = self.config.filepaths.track_file.format(
            tracknum=track_num or 0,
            artist=sanitize_filename(track_artist),
            title=sanitize_filename(track_title),
            ext=ext,
        )
        dest_dir = Path(self.config.core.download_path) / album_folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / track_file
        dest = validate_path_length(dest)
        shutil.move(str(source), str(dest))
        logger.info("Moved %s -> %s", source.name, dest)
        return dest

    def process_track(
        self,
        source: Path,
        album_id: int,
        track_id: int,
        album_artist: str,
        album_title: str,
        year: int | None,
        track_num: int | None,
        track_artist: str,
        track_title: str,
        service: str,
        quality: int | None = None,
    ) -> Path | None:
        if not self.verify_file(source):
            return None

        checksum = self.compute_checksum(source)
        ext = source.suffix.lower()

        dest = self.move_to_library(
            source,
            album_artist, album_title, year,
            track_num, track_artist, track_title, ext,
        )

        audio = mutagen.File(str(dest))
        info = audio.info if audio else None
        self.repo.update_track_file(
            track_id=track_id,
            file_path=str(dest),
            file_format=ext.lstrip(".").upper(),
            bitrate=getattr(info, "bitrate", None),
            sample_rate=getattr(info, "sample_rate", None),
            bit_depth=getattr(info, "bit_depth", None),
        )

        self.repo.add_download_log(
            track_id=track_id,
            service=service,
            quality=quality,
            file_path=str(dest),
            file_size=dest.stat().st_size,
            checksum=checksum,
        )

        logger.info("Registered track %d -> %s", track_id, dest)
        return dest
