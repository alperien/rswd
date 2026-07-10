from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def ensure_schema(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        try:
            current = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                current = 0
            else:
                raise

        migrations = sorted(MIGRATIONS_DIR.glob("v*.sql"))
        for migration in migrations:
            match = re.match(r"v(\d+)_", migration.stem)
            if not match:
                continue
            version = int(match.group(1))
            if version <= current:
                stored = conn.execute(
                    "SELECT checksum FROM schema_version WHERE version = ?",
                    (version,),
                ).fetchone()
                if stored:
                    sql = migration.read_text(encoding="utf-8")
                    actual = hashlib.sha256(sql.encode()).hexdigest()
                    if actual != stored[0]:
                        raise RuntimeError(
                            f"Checksum mismatch for migration {migration.stem}: "
                            f"expected {stored[0]}, got {actual}"
                        )
                continue
            sql = migration.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            conn.execute("BEGIN")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version, checksum) VALUES (?, ?)",
                (version, checksum),
            )
            conn.execute("COMMIT")
            logger.info("Applied DB migration %s", migration.stem)
    finally:
        conn.close()
