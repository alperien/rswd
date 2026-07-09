from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path
from typing import Optional

from rswd.db.models import Album, Artist, DownloadLogEntry, SchedulerLogEntry, Track


def _unicode_nocase(a: str, b: str) -> int:
    a = unicodedata.normalize("NFC", a).casefold()
    b = unicodedata.normalize("NFC", b).casefold()
    return (a > b) - (a < b)


class Repository:
    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path).resolve())
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.create_collation("UNICODE_NOCASE", _unicode_nocase)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Repository":
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    # --- Artists ---

    def add_artist(
        self,
        name: str,
        sort_name: str | None = None,
        mb_artistid: str | None = None,
        is_monitored: bool = False,
        monitor_quality: int = 2,
        metadata_blob: str | None = None,
    ) -> int:
        conn = self.connect()
        cur = conn.execute(
            """INSERT INTO artists (name, sort_name, mb_artistid, is_monitored, monitor_quality, metadata_blob)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, sort_name, mb_artistid, int(is_monitored), monitor_quality, metadata_blob),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_artist(self, artist_id: int) -> Optional[Artist]:
        row = self.connect().execute(
            "SELECT * FROM artists WHERE id = ?", (artist_id,)
        ).fetchone()
        return self._row_to_artist(row) if row else None

    def get_artist_by_name(self, name: str) -> Optional[Artist]:
        row = self.connect().execute(
            "SELECT * FROM artists WHERE name = ? COLLATE UNICODE_NOCASE", (name,)
        ).fetchone()
        return self._row_to_artist(row) if row else None

    def list_artists(self, monitored_only: bool = False) -> list[Artist]:
        query = "SELECT * FROM artists"
        params: tuple = ()
        if monitored_only:
            query += " WHERE is_monitored = 1"
        query += " ORDER BY name COLLATE UNICODE_NOCASE"
        rows = self.connect().execute(query, params).fetchall()
        return [self._row_to_artist(r) for r in rows]

    def remove_artist(self, artist_id: int) -> bool:
        conn = self.connect()
        cur = conn.execute("DELETE FROM artists WHERE id = ?", (artist_id,))
        conn.commit()
        return cur.rowcount > 0

    def set_monitored(self, artist_id: int, monitored: bool) -> bool:
        conn = self.connect()
        cur = conn.execute(
            "UPDATE artists SET is_monitored = ? WHERE id = ?",
            (int(monitored), artist_id),
        )
        conn.commit()
        return cur.rowcount > 0

    # --- Albums ---

    def add_album(
        self,
        artist_id: int,
        title: str,
        year: int | None = None,
        album_type: str | None = None,
        mb_albumid: str | None = None,
        total_tracks: int | None = None,
        service: str | None = None,
        service_id: str | None = None,
        quality_tier: int | None = None,
        metadata_blob: str | None = None,
    ) -> int:
        conn = self.connect()
        cur = conn.execute(
            """INSERT INTO albums (artist_id, title, year, album_type, mb_albumid, total_tracks,
               service, service_id, quality_tier, metadata_blob)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (artist_id, title, year, album_type, mb_albumid, total_tracks,
             service, service_id, quality_tier, metadata_blob),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def album_exists(self, artist_id: int, title: str, year: int | None = None) -> bool:
        if year is not None:
            row = self.connect().execute(
                "SELECT 1 FROM albums WHERE artist_id = ? AND title = ? COLLATE UNICODE_NOCASE AND year = ?",
                (artist_id, title, year),
            ).fetchone()
        else:
            row = self.connect().execute(
                "SELECT 1 FROM albums WHERE artist_id = ? AND title = ? COLLATE UNICODE_NOCASE",
                (artist_id, title),
            ).fetchone()
        return row is not None

    def get_album(self, album_id: int) -> Optional[Album]:
        row = self.connect().execute(
            "SELECT * FROM albums WHERE id = ?", (album_id,)
        ).fetchone()
        return self._row_to_album(row) if row else None

    def list_albums(
        self,
        artist_id: int | None = None,
        status: str | None = None,
    ) -> list[Album]:
        query = "SELECT * FROM albums WHERE 1=1"
        params: list = []
        if artist_id is not None:
            query += " AND artist_id = ?"
            params.append(artist_id)
        if status:
            query += " AND download_status = ?"
            params.append(status)
        query += " ORDER BY year DESC, title COLLATE UNICODE_NOCASE"
        rows = self.connect().execute(query, params).fetchall()
        return [self._row_to_album(r) for r in rows]

    def update_album_status(self, album_id: int, status: str, quality_tier: int | None = None):
        conn = self.connect()
        if quality_tier is not None:
            conn.execute(
                "UPDATE albums SET download_status = ?, quality_tier = ? WHERE id = ?",
                (status, quality_tier, album_id),
            )
        else:
            conn.execute(
                "UPDATE albums SET download_status = ? WHERE id = ?",
                (status, album_id),
            )
        conn.commit()

    # --- Tracks ---

    def add_track(
        self,
        album_id: int,
        title: str,
        track_number: int | None = None,
        disc_number: int = 1,
        duration: float | None = None,
        artist: str | None = None,
        isrc: str | None = None,
        mb_recording_id: str | None = None,
        service_id: str | None = None,
    ) -> int:
        conn = self.connect()
        cur = conn.execute(
            """INSERT INTO tracks (album_id, title, track_number, disc_number, duration, artist,
               isrc, mb_recording_id, service_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (album_id, title, track_number, disc_number, duration, artist,
             isrc, mb_recording_id, service_id),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def update_track_file(
        self,
        track_id: int,
        file_path: str,
        file_format: str,
        bitrate: int | None = None,
        sample_rate: int | None = None,
        bit_depth: int | None = None,
    ):
        conn = self.connect()
        conn.execute(
            """UPDATE tracks SET file_path = ?, file_format = ?, bitrate = ?,
               sample_rate = ?, bit_depth = ?, download_status = 'downloaded'
               WHERE id = ?""",
            (file_path, file_format, bitrate, sample_rate, bit_depth, track_id),
        )
        conn.commit()

    def list_tracks(self, album_id: int) -> list[Track]:
        rows = self.connect().execute(
            "SELECT * FROM tracks WHERE album_id = ? ORDER BY disc_number, track_number",
            (album_id,),
        ).fetchall()
        return [self._row_to_track(r) for r in rows]

    def get_track_by_path(self, file_path: str) -> Optional[Track]:
        row = self.connect().execute(
            "SELECT * FROM tracks WHERE file_path = ?", (file_path,)
        ).fetchone()
        return self._row_to_track(row) if row else None

    # --- Download Log ---

    def add_download_log(
        self,
        track_id: int,
        service: str,
        quality: int | None = None,
        file_path: str | None = None,
        file_size: int | None = None,
        checksum: str | None = None,
    ) -> int:
        conn = self.connect()
        cur = conn.execute(
            """INSERT INTO download_log (track_id, service, quality, file_path, file_size, checksum)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (track_id, service, quality, file_path, file_size, checksum),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    # --- Library stats ---

    def library_stats(self) -> dict:
        conn = self.connect()
        artists = conn.execute("SELECT COUNT(*) FROM artists").fetchone()[0]
        albums = conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
        tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        downloaded = conn.execute(
            "SELECT COUNT(*) FROM tracks WHERE download_status = 'downloaded'"
        ).fetchone()[0]
        return {
            "artists": artists,
            "albums": albums,
            "tracks": tracks,
            "downloaded": downloaded,
        }

    # --- Row mapping ---

    @staticmethod
    def _row_to_artist(row: sqlite3.Row) -> Artist:
        return Artist(
            id=row["id"],
            name=row["name"],
            sort_name=row["sort_name"],
            mb_artistid=row["mb_artistid"],
            is_monitored=bool(row["is_monitored"]),
            monitor_quality=row["monitor_quality"],
            added_at=row["added_at"],
            metadata_blob=row["metadata_blob"],
        )

    @staticmethod
    def _row_to_album(row: sqlite3.Row) -> Album:
        return Album(
            id=row["id"],
            artist_id=row["artist_id"],
            title=row["title"],
            year=row["year"],
            album_type=row["album_type"],
            mb_albumid=row["mb_albumid"],
            mb_release_groupid=row["mb_release_groupid"],
            total_tracks=row["total_tracks"],
            download_status=row["download_status"],
            quality_tier=row["quality_tier"],
            service=row["service"],
            service_id=row["service_id"],
            added_at=row["added_at"],
            metadata_blob=row["metadata_blob"],
        )

    @staticmethod
    def _row_to_track(row: sqlite3.Row) -> Track:
        return Track(
            id=row["id"],
            album_id=row["album_id"],
            title=row["title"],
            track_number=row["track_number"],
            disc_number=row["disc_number"],
            duration=row["duration"],
            artist=row["artist"],
            file_path=row["file_path"],
            file_format=row["file_format"],
            bitrate=row["bitrate"],
            sample_rate=row["sample_rate"],
            bit_depth=row["bit_depth"],
            isrc=row["isrc"],
            mb_recording_id=row["mb_recording_id"],
            service_id=row["service_id"],
            download_status=row["download_status"],
            added_at=row["added_at"],
        )
