CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    checksum TEXT
);

CREATE TABLE IF NOT EXISTS artists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    sort_name       TEXT,
    mb_artistid     TEXT UNIQUE,
    is_monitored    INTEGER NOT NULL DEFAULT 0,
    monitor_quality INTEGER DEFAULT 2,
    added_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    metadata_blob   TEXT
);

CREATE INDEX IF NOT EXISTS idx_artists_name ON artists(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_artists_monitored ON artists(is_monitored);
CREATE INDEX IF NOT EXISTS idx_artists_mbid ON artists(mb_artistid);

CREATE TABLE IF NOT EXISTS albums (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_id       INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    year            INTEGER,
    album_type      TEXT,
    mb_albumid      TEXT,
    mb_release_groupid TEXT,
    total_tracks    INTEGER,
    download_status TEXT NOT NULL DEFAULT 'none',
    quality_tier    INTEGER,
    service         TEXT,
    service_id      TEXT,
    added_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    metadata_blob   TEXT,
    UNIQUE(artist_id, title)
);

CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist_id);
CREATE INDEX IF NOT EXISTS idx_albums_title ON albums(title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_albums_status ON albums(download_status);
CREATE INDEX IF NOT EXISTS idx_albums_mbid ON albums(mb_albumid);

CREATE TABLE IF NOT EXISTS tracks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id        INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    track_number    INTEGER,
    disc_number     INTEGER DEFAULT 1,
    duration        REAL,
    artist          TEXT,
    file_path       TEXT,
    file_format     TEXT,
    bitrate         INTEGER,
    sample_rate     INTEGER,
    bit_depth       INTEGER,
    isrc            TEXT,
    mb_recording_id TEXT,
    service_id      TEXT,
    download_status TEXT NOT NULL DEFAULT 'pending',
    added_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(download_status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_path ON tracks(file_path) WHERE file_path IS NOT NULL;

CREATE TABLE IF NOT EXISTS download_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id        INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    service         TEXT NOT NULL,
    quality         INTEGER,
    file_path       TEXT,
    file_size       INTEGER,
    checksum        TEXT,
    downloaded_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_dl_log_track ON download_log(track_id);

CREATE TABLE IF NOT EXISTS scheduler_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name        TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    status          TEXT NOT NULL,
    message         TEXT,
    albums_found    INTEGER DEFAULT 0,
    tracks_added    INTEGER DEFAULT 0,
    tracks_dled     INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sched_log_job ON scheduler_log(job_name);
