from __future__ import annotations

import hashlib
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def ensure_schema(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        current = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_version"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        current = 0

    migrations = sorted(MIGRATIONS_DIR.glob("v*.sql"))
    for migration in migrations:
        version = int(migration.stem.split("v")[1].split("_")[0])
        if version <= current:
            continue
        sql = migration.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode()).hexdigest()
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_version (version, checksum) VALUES (?, ?)",
            (version, checksum),
        )
        conn.commit()
        logger.info("Applied DB migration %s", migration.stem)

    conn.close()
