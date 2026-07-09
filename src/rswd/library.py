from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import mutagen

from rswd.db.repository import Repository

logger = logging.getLogger("rswd.library")

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aiff", ".wma"}


class LibraryScanner:
    def __init__(self, repo: Repository):
        self.repo = repo

    def scan_directory(self, directory: str) -> dict[str, int]:
        stats: dict[str, int] = {"scanned": 0, "matched": 0, "imported": 0, "errors": 0}
        root = Path(directory)
        if not root.is_dir():
            logger.error("Scan directory not found: %s", directory)
            return stats

        for path in root.rglob("*"):
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            stats["scanned"] += 1
            try:
                result = self._process_file(path)
                if result == "matched":
                    stats["matched"] += 1
                elif result == "imported":
                    stats["imported"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
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
        except mutagen.MutagenError:
            return "skipped"

        tags = audio.tags or {}
        title = self._tag_value(tags, "title")
        artist = self._tag_value(tags, "artist")
        album_title = self._tag_value(tags, "album")
        track_number = self._tag_int(tags, "tracknumber")
        album_artist = self._tag_value(tags, "albumartist") or artist

        if not title or not artist or not album_title:
            return "skipped"

        if album_artist is None:
            return "skipped"
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

        year = self._tag_int(tags, "date") or self._tag_int(tags, "year")
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

        tid = self.repo.add_track(
            album_id=db_album.id,
            title=title,
            track_number=track_number,
            disc_number=self._tag_int(tags, "discnumber") or 1,
            duration=self._get_duration(audio),
            artist=artist,
        )

        info = audio.info if audio else None
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

    def prune_missing(self) -> int:
        conn = self.repo.connect()
        rows = conn.execute(
            "SELECT id, file_path FROM tracks WHERE file_path IS NOT NULL"
        ).fetchall()
        removed = 0
        for row in rows:
            if not Path(row["file_path"]).is_file():
                conn.execute(
                    "UPDATE tracks SET file_path = NULL, download_status = 'missing' WHERE id = ?",
                    (row["id"],),
                )
                removed += 1
        conn.commit()
        logger.info("Pruned %d missing tracks", removed)
        return removed

    @staticmethod
    def _tag_value(tags, key: str) -> Optional[str]:
        for fmt_key in (key, key.upper(), key.capitalize()):
            val = tags.get(fmt_key)
            if val:
                if isinstance(val, list):
                    val = val[0]
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
        except Exception:
            return None
