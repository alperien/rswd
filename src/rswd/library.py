from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

import mutagen

from rswd.db.repository import Repository

logger = logging.getLogger("rswd.library")

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aiff", ".wma"}

_TAG_MAP = {
    "title": ("title", "TITLE", "TIT2"),
    "artist": ("artist", "ARTIST", "TPE1"),
    "album": ("album", "ALBUM", "TALB"),
    "albumartist": ("albumartist", "ALBUMARTIST", "TPE2"),
    "date": ("date", "DATE", "TDRC", "TDOR"),
    "track": ("track", "TRACK", "TRCK"),
    "disc": ("disc", "DISC", "TPOS"),
    "genre": ("genre", "GENRE", "TCON"),
}


class LibraryScanner:
    def __init__(self, repo: Repository):
        self.repo = repo

    def scan_directory(self, directory: str) -> dict[str, int]:
        stats: dict[str, int] = {"scanned": 0, "matched": 0, "imported": 0, "errors": 0}
        root = Path(directory)
        if not root.is_dir():
            logger.error("Scan directory not found: %s", directory)
            return stats

        # Note: rglob("*") materializes all paths into memory; large directory trees may cause high memory usage.
        entries = list(root.rglob("*"))
        for path in entries:
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            stats["scanned"] += 1
            try:
                result = self._process_file(path)
                if result == "matched":
                    stats["matched"] += 1
                elif result == "imported":
                    stats["imported"] += 1
                elif result == "skipped":
                    pass
                else:
                    stats["errors"] += 1
            except (OSError, sqlite3.Error) as e:
                logger.error("Error processing %s: %s", path, e)
                stats["errors"] += 1

        return stats

    def _process_file(self, path: Path) -> str:
        str_path = str(path)
        existing = self.repo.get_track_by_path(str_path)
        if existing:
            return "matched"

        try:
            audio = mutagen.File(str_path)
            if audio is None:
                return "skipped"
        except (mutagen.MutagenError, OSError):
            return "skipped"

        tags = audio.tags or {}
        title = self._tag_value(tags, "title")
        artist = self._tag_value(tags, "artist")
        album_title = self._tag_value(tags, "album")
        track_number = self._tag_int(tags, "tracknumber")
        album_artist = self._tag_value(tags, "albumartist") or artist

        if not title or not artist or not album_title:
            return "skipped"

        if not isinstance(album_artist, str):
            raise TypeError(f"album_artist must be str, got {type(album_artist)}")

        db_artist = self.repo.get_artist_by_name(album_artist)
        if not db_artist:
            aid = self.repo.add_artist(
                name=album_artist,
                sort_name=self._tag_value(tags, "artistsort"),
                is_monitored=False,
            )
            db_artist = self.repo.get_artist(aid)
        if db_artist is None:
            return "skipped"

        db_album = None
        for a in self.repo.list_albums(artist_id=db_artist.id):
            if a.title.lower() == album_title.lower():
                db_album = a
                break

        year = self._tag_int(tags, "date")
        if year is None:
            year = self._tag_int(tags, "year")
        if not db_album:
            alid = self.repo.add_album(
                artist_id=db_artist.id,
                title=album_title,
                year=year,
                album_type=self._tag_value(tags, "albumtype"),
                total_tracks=self._tag_int(tags, "tracktotal"),
            )
            db_album = self.repo.get_album(alid)
            if db_album is None:
                return "skipped"

        disc_int = self._tag_int(tags, "discnumber")
        tid = self.repo.add_track(
            album_id=db_album.id,
            title=title,
            track_number=track_number,
            disc_number=disc_int if disc_int is not None else 1,
            duration=self._get_duration(audio),
            artist=artist,
        )

        info = audio.info
        self.repo.update_track_file(
            track_id=tid,
            file_path=str_path,
            file_format=path.suffix.lstrip(".").upper(),
            bitrate=getattr(info, "bitrate", None),
            sample_rate=getattr(info, "sample_rate", None),
            bit_depth=getattr(info, "bit_depth", None),
        )

        logger.info("Imported %s -> track %d", path, tid)
        return "imported"

    def preview_directory(self, directory: str) -> dict[str, int]:
        stats: dict[str, int] = {"scanned": 0, "matched": 0, "imported": 0, "errors": 0}
        root = Path(directory)
        if not root.is_dir():
            logger.error("Preview directory not found: %s", directory)
            return stats

        entries = list(root.rglob("*"))
        for path in entries:
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            stats["scanned"] += 1
            try:
                existing = self.repo.get_track_by_path(str(path))
                if existing:
                    stats["matched"] += 1
                    continue
                audio = mutagen.File(str(path))
                if audio is None:
                    continue
                tags = audio.tags or {}
                title = self._tag_value(tags, "title")
                artist = self._tag_value(tags, "artist")
                album_title = self._tag_value(tags, "album")
                if title and artist and album_title:
                    stats["imported"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                logger.error("Error previewing %s: %s", path, e)
                stats["errors"] += 1

        return stats

    def prune_missing(self) -> int:
        conn = self.repo.connect()
        cursor = conn.execute(
            "SELECT id, file_path FROM tracks WHERE file_path IS NOT NULL"
        )
        removed = 0
        while True:
            rows = cursor.fetchmany(100)
            if not rows:
                break
            for row in rows:
                try:
                    if not Path(row["file_path"]).is_file():
                        conn.execute(
                            "UPDATE tracks SET file_path = NULL, download_status = 'missing' WHERE id = ?",
                            (row["id"],),
                        )
                        conn.commit()
                        removed += 1
                except Exception as e:
                    logger.warning("Error checking track %s: %s", row["id"], e)
        logger.info("Pruned %d missing tracks", removed)
        return removed

    @staticmethod
    def _tag_value(tags, key: str) -> Optional[str]:
        keys_to_try = _TAG_MAP.get(key, (key,))
        for fmt_key in keys_to_try:
            val = tags.get(fmt_key)
            if not val:
                continue
            if hasattr(val, "text"):
                text_list = val.text
                if text_list:
                    return str(text_list[0]).strip()
                continue
            if isinstance(val, list):
                if val:
                    return str(val[0]).strip()
                continue
            return str(val).strip()
        return None

    @staticmethod
    def _tag_int(tags, key: str) -> Optional[int]:
        val = LibraryScanner._tag_value(tags, key)
        if val is None:
            return None
        try:
            return int(val.split("/")[0])
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _get_duration(audio) -> Optional[float]:
        try:
            return audio.info.length
        except Exception as e:
            logger.debug("Could not get duration: %s", e)
            return None
