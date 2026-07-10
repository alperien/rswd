import sqlite3

from rswd.db.schema import ensure_schema


def test_schema_creates_tables(tmp_path):
    db = str(tmp_path / "test.db")
    ensure_schema(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    expected = {"schema_version", "artists", "albums", "tracks", "download_log", "scheduler_log"}
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"
    conn.close()


def test_schema_is_idempotent(tmp_path):
    db = str(tmp_path / "test.db")
    ensure_schema(db)
    ensure_schema(db)  # second call should not raise
    conn = sqlite3.connect(db)
    version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert version == 1
    conn.close()


def test_foreign_keys_enabled(tmp_path):
    db = str(tmp_path / "test.db")
    ensure_schema(db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    fk_enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk_enabled == 1
    conn.close()


def test_wal_mode(tmp_path):
    db = str(tmp_path / "test.db")
    ensure_schema(db)
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    conn.close()
