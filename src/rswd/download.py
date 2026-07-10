from __future__ import annotations

import hashlib
import logging
import re
import shutil
import time
from pathlib import Path

import mutagen

from rswd.config import ConfigData
from rswd.db.repository import Repository
from rswd.util import sanitize_filename, validate_path_length

logger = logging.getLogger("rswd.download")


class DownloadPipeline:
    def __init__(self, config: ConfigData, repo: Repository):
        self.config = config
        self.repo = repo

    def _extract_audio_info(self, file_path: Path) -> tuple[bool, object | None]:
        try:
            audio = mutagen.File(str(file_path))
            if audio is None:
                return False, None
            return True, getattr(audio, "info", None)
        except mutagen.MutagenError as e:
            logger.error("Invalid audio file %s: %s", file_path, e)
            return False, None

    def verify_file(self, file_path: Path) -> bool:
        if not file_path.is_file():
            logger.error("File not found: %s", file_path)
            return False
        if file_path.stat().st_size == 0:
            logger.error("File is empty: %s", file_path)
            return False
        ok, _ = self._extract_audio_info(file_path)
        return ok

    def compute_checksum(self, file_path: Path) -> str | None:
        try:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        except OSError as e:
            logger.error("Failed to compute checksum for %s: %s", file_path, e)
            return None

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
        if not album_artist or not album_artist.strip():
            album_artist = "Unknown Artist"
        if not album_title or not album_title.strip():
            album_title = "Unknown Album"
        if not track_artist or not track_artist.strip():
            track_artist = "Unknown Artist"
        if not track_title or not track_title.strip():
            track_title = "Unknown Track"

        download_path = Path(self.config.core.download_path).resolve()

        year_part = "" if year is None else str(year)

        try:
            album_folder = self.config.filepaths.album_folder.format(
                albumartist=sanitize_filename(album_artist),
                album=sanitize_filename(album_title),
                year=year_part,
            )
        except KeyError as e:
            logger.error("Invalid album_folder format string: missing key %s", e)
            raise ValueError(f"album_folder format string missing key: {e}") from e

        if year is None:
            album_folder = re.sub(r"\s*\([^)]*\)\s*$", "", album_folder)
            album_folder = re.sub(r"\s*\[[^\]]*\]\s*$", "", album_folder)

        track_num_val = track_num if track_num is not None else 0

        try:
            track_file = self.config.filepaths.track_file.format(
                tracknum=track_num_val,
                artist=sanitize_filename(track_artist),
                title=sanitize_filename(track_title),
                ext=ext,
            )
        except KeyError as e:
            logger.error("Invalid track_file format string: missing key %s", e)
            raise ValueError(f"track_file format string missing key: {e}") from e

        dest_dir = download_path / album_folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / track_file

        try:
            dest = validate_path_length(dest)
        except OSError as e:
            logger.error("Path validation failed: %s", e)
            raise

        resolved_dest = dest.resolve()
        try:
            resolved_dest.relative_to(download_path)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: {resolved_dest} is outside {download_path}"
            )

        if dest.exists():
            stem, ext_part = dest.stem, dest.suffix
            counter = 1
            while dest.exists():
                deduped = dest_dir / f"{stem} ({counter}){ext_part}"
                try:
                    deduped = validate_path_length(deduped)
                except OSError:
                    logger.error("Deduped path too long: %s", deduped)
                    raise
                resolved_deduped = deduped.resolve()
                try:
                    resolved_deduped.relative_to(download_path)
                except ValueError:
                    raise ValueError(
                        f"Path traversal detected after dedup: {resolved_deduped}"
                    )
                dest = deduped
                counter += 1

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                shutil.move(str(source), str(dest))
                break
            except (OSError, PermissionError) as e:
                last_err = e
                if attempt < 2:
                    logger.warning(
                        "Move attempt %d failed for %s: %s, retrying...",
                        attempt + 1, source.name, e,
                    )
                    time.sleep(0.5 * (attempt + 1))
        else:
            logger.error("Failed to move %s after 3 attempts: %s", source.name, last_err)
            raise last_err  # type: ignore[misc]

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
        ok, audio_info = self._extract_audio_info(source)
        if not ok:
            if not source.is_file():
                logger.error("File not found: %s", source)
            elif source.stat().st_size == 0:
                logger.error("File is empty: %s", source)
            return None

        checksum = self.compute_checksum(source)
        ext = source.suffix.lower()
        if not ext:
            ext = ".bin"

        dest = self.move_to_library(
            source,
            album_artist, album_title, year,
            track_num, track_artist, track_title, ext,
        )

        track_file_updated = False
        try:
            format_upper = ext.removeprefix(".").upper()

            updated = self.repo.update_track_file(
                track_id=track_id,
                file_path=str(dest),
                file_format=format_upper,
                bitrate=getattr(audio_info, "bitrate", None),
                sample_rate=getattr(audio_info, "sample_rate", None),
                bit_depth=getattr(audio_info, "bit_depth", None),
            )
            if not updated:
                logger.error("update_track_file returned false for track %d", track_id)
                raise RuntimeError(f"update_track_file failed for track {track_id}")
            track_file_updated = True

            self.repo.add_download_log(
                track_id=track_id,
                service=service,
                quality=quality,
                file_path=str(dest),
                file_size=dest.stat().st_size,
                checksum=checksum,
            )
        except (OSError, mutagen.MutagenError, RuntimeError) as e:
            logger.error("Failed to register track %d after move: %s", track_id, e)
            if track_file_updated:
                try:
                    self.repo.update_track_file(
                        track_id=track_id,
                        file_path="",
                        file_format="",
                        bitrate=None,
                        sample_rate=None,
                        bit_depth=None,
                    )
                except (OSError, RuntimeError) as revert_err:
                    logger.error(
                        "Failed to revert track %d DB state: %s", track_id, revert_err
                    )
            try:
                shutil.move(str(dest), str(source))
                logger.info("Rolled back %s -> %s", dest, source)
            except OSError as rollback_err:
                logger.error("Rollback also failed for %s: %s", dest, rollback_err)
            return None

        logger.info("Registered track %d -> %s", track_id, dest)
        return dest
