# rswd-cli: Architecture & Technical Specification

**Status:** Planning / Pre-Implementation
**Target Python:** 3.11+
**License:** MIT
**Repository:** `rswd-cli/`

---

## 1. Executive Summary

A lightweight CLI-based rswd alternative that replaces the traditional multi-stage pipeline (indexer → RSS → downloader → post-processor) with a **single-stage streaming-service pipeline**. The streaming services (Deezer, Tidal, Qobuz, Apple Music, etc.) serve simultaneously as:
- **Indexer** (search their catalog for artists/albums/tracks)
- **Metadata provider** (track titles, artists, album art, ISRCs, labels)
- **Download source** (direct stream download or encrypted stream decryption)

This eliminates RSS, Usenet, BitTorrent, quality-profiles-as-version-matching, and the entire release-matching problem space. The "rswd" part is reduced to: artist subscription management, periodic polling for new releases, and automated downloading.

---

## 2. System Architecture

### 2.1 Layer Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLI Layer (Click)                             │
│  artist add/list/remove/monitor   album search/download/list          │
│  library status/import   daemon start/stop/status                    │
├──────────────────────────────────────────────────────────────────────┤
│                        Application Layer                              │
│  ┌──────────────┐  ┌──────────────────┐  ┌────────────────────────┐  │
│  │ Library Mgr  │  │ Monitor Engine   │  │ Download Controller    │  │
│  │  (CRUD ops)  │  │  (new release    │  │  (orchestrate backend) │  │
│  │              │  │   detection)     │  │                        │  │
│  └──────┬───────┘  └────────┬─────────┘  └───────────┬────────────┘  │
│         │                   │                          │               │
├─────────┼───────────────────┼──────────────────────────┼──────────────┤
│         ▼                   ▼                          ▼               │
│  ┌──────────┐       ┌──────────┐              ┌──────────────────┐   │
│  │ SQLite   │       │Scheduler │              │  Backend          │   │
│  │  (DB)    │       │APSched.  │              │   Abstraction     │   │
│  └──────────┘       └──────────┘              │    Layer          │   │
│                                                └────────┬─────────┘   │
├─────────────────────────────────────────────────────────┼─────────────┤
│                                                          │              │
│                                          ┌───────────────┴──────────┐ │
│                                          │    Download Backend(s)    │ │
│                     ┌────────────────────├──────────────────────────┤ │
│                     │   streamrip        │   OrpheusDL (optional)    │ │
│                     │   (primary)        │   (extended services)     │ │
│                     └────────┬───────────┴────────────┬─────────────┘ │
│                              │                        │               │
│                    ┌─────────┴──────────┐   ┌─────────┴──────────┐   │
│                    │ Deezer  │  Tidal   │   │ Apple Mu │ Spotify  │   │
│                    │ Qobuz   │SoundCloud│   │ YouTube  │ ...      │   │
│                    └────────────────────┘   └────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Dependency Diagram

```
rswd-cli (this project)
  ├── streamrip [pip]        -- Primary download backend
  │     ├── aiohttp          -- Async HTTP
  │     ├── mutagen          -- Tagging
  │     ├── click            -- CLI framework
  │     └── rich             -- Terminal UI
  ├── musicbrainzngs [pip]   -- Optional metadata enrichment
  ├── click [pip]            -- CLI framework
  ├── rich [pip]             -- Tables, progress bars, formatting
  ├── apscheduler [pip]      -- Job scheduling
  ├── tomli [stdlib 3.11+]   -- TOML parsing
  └── sqlite3 [stdlib]       -- Database
```

### 2.3 Project Structure

```
rswd-cli/
├── pyproject.toml              # PEP 621 project metadata
├── README.md
├── LICENSE
├── plans/
│   └── architecture.md         # ← this document
├── src/
│   └── rswd/
│       ├── __init__.py
│       ├── __main__.py         # `python -m rswd` entry
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── app.py          # Click root group + global options
│       │   ├── artist.py       # artist add|list|remove|monitor|unmonitor
│       │   ├── album.py        # album search|download|list
│       │   ├── library.py      # library status|import|scan
│       │   └── daemon.py       # daemon start|stop|status
│       ├── db/
│       │   ├── __init__.py
│       │   ├── schema.py       # DDL + migration applied at import
│       │   ├── models.py       # Python dataclass models (not ORM)
│       │   └── repository.py   # All SQL queries, parameterized
│       ├── backends/
│       │   ├── __init__.py     # backend factory: get_backend(name)
│       │   ├── base.py         # AbstractSearchDownloadBackend ABC
│       │   ├── streamrip_.py   # StreamripBackend implementation
│       │   └── orpheus.py      # OrpheusBackend implementation
│       ├── metadata/
│       │   ├── __init__.py
│       │   ├── musicbrainz.py  # MusicBrainz enrichment (optional)
│       │   └── normalizer.py   # Title/artist string normalization
│       ├── scheduler/
│       │   ├── __init__.py
│       │   └── jobs.py         # check_new_releases() job definition
│       ├── config.py           # Config loading, validation, defaults
│       └── util.py             # Path helpers, sanitization, logging
├── tests/
│   ├── conftest.py
│   ├── test_db/
│   ├── test_backends/
│   └── test_cli/
└── config.toml.example
```

---

## 3. Component Specification

### 3.1 Config System (`src/rswd/config.py`)

#### 3.1.1 Format: TOML (via `tomli` stdlib)

`tomli` is in the stdlib since Python 3.11. The config is loaded once at CLI startup and exposed as a frozen dataclass.

#### 3.1.2 Config Schema

```toml
# config.toml
[core]
download_path = "~/music"          # Where organized music lives
library_db = "~/.local/share/rswd/library.db"
jobs_db = "~/.local/share/rswd/jobs.db"
log_level = "INFO"

[daemon]
enabled = false                    # Start daemon at boot?
check_interval_hours = 24
check_at_startup = true

[quality]
default = 2                        # 0=128k, 1=320k, 2=CD/16.44, 3=HiRes/24b
codec = "FLAC"                     # FLAC, ALAC, MP3, AAC
concurrency = 3

[filepaths]
# Python format-string templates:
# Album output directory template
album_folder = "{albumartist}/{album} ({year})"
# Individual track filename template
track_file = "{tracknum:02d}. {artist} - {title}{ext}"

[metadata]
embed_cover = true
cover_size = 1400
embed_lyrics = true
musicbrainz = true                 # Enrich with MusicBrainz metadata

[backend]
name = "streamrip"                 # streamrip | orpheusdl

# streamrip-specific overrides (optional)
# If blank, streamrip's own ~/.config/streamrip/config.toml is used
[backend.streamrip]
config_path = ""

# OrpheusDL-specific overrides (optional)
[backend.orpheusdl]
install_path = ""

# --- Service Credentials ---
# Only configure the services you subscribe to.

[services.deezer]
# ARL cookie from browser dev tools (Deezer session cookie)
arl = ""

[services.tidal]
access_token = ""
refresh_token = ""
user_id = ""
country_code = ""
token_expiry = ""

[services.qobuz]
email_or_userid = ""
password_or_token = ""
app_id = ""
secrets = []

[services.soundcloud]
client_id = ""
app_version = ""
```

#### 3.1.3 Config Resolution Order

1. Built-in defaults (defined in `config.py`)
2. `~/.config/rswd/config.toml` (default path, overridable via `--config`)
3. Environment variables `rswd_*` (future)
4. CLI flags (`--download-path`, `--quality`)

### 3.2 Database Schema (`src/rswd/db/schema.py`)

#### 3.2.1 Entity-Relationship Diagram

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   artists     │     │    albums         │     │    tracks         │
├──────────────┤     ├──────────────────┤     ├──────────────────┤
│ id (PK)      │◄────│ artist_id (FK)   │◄────│ album_id (FK)    │
│ name         │     │ id (PK)          │     │ id (PK)          │
│ sort_name    │     │ title            │     │ title            │
│ mb_artistid  │     │ year             │     │ track_number     │
│ is_monitored │     │ mb_albumid       │     │ disc_number      │
│ monitor_qual │     │ album_type       │     │ duration         │
│ added_at     │     │ total_tracks     │     │ artist           │
│ metadata_blob│     │ download_status  │     │ file_path        │
└──────────────┘     │ quality_tier     │     │ file_format      │
                      │ service          │     │ bitrate          │
                      │ service_id       │     │ sample_rate      │
                      │ added_at         │     │ bit_depth        │
                      │ metadata_blob    │     │ isrc             │
                      └──────────────────┘     │ mb_recording_id │
                           │                   │ service_id      │
                           │                   │ download_status │
                           │                   │ added_at        │
                           │                   └──────────────────┘
                           │
                           ▼
                    ┌──────────────────┐
                    │ download_log     │
                    ├──────────────────┤
                    │ id (PK)          │
                    │ track_id (FK)    │
                    │ service          │
                    │ quality          │
                    │ file_path        │
                    │ file_size        │
                    │ downloaded_at    │
                    │ checksum (SHA256)│
                    └──────────────────┘
```

#### 3.2.2 DDL

```sql
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Artists
CREATE TABLE IF NOT EXISTS artists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    sort_name       TEXT,
    mb_artistid     TEXT UNIQUE,
    is_monitored    INTEGER NOT NULL DEFAULT 0,
    monitor_quality INTEGER DEFAULT 2,
    added_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    metadata_blob   TEXT          -- JSON blob: cached service metadata
);

CREATE INDEX IF NOT EXISTS idx_artists_name ON artists(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_artists_monitored ON artists(is_monitored);
CREATE INDEX IF NOT EXISTS idx_artists_mbid ON artists(mb_artistid);

-- Albums
CREATE TABLE IF NOT EXISTS albums (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_id       INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    year            INTEGER,
    album_type      TEXT,          -- 'album', 'single', 'ep', 'compilation', 'live'
    mb_albumid      TEXT,
    mb_release_groupid TEXT,
    total_tracks    INTEGER,
    download_status TEXT NOT NULL DEFAULT 'none',
                    -- 'none' | 'partial' | 'complete' | 'upgradable'
    quality_tier    INTEGER,
    service         TEXT,          -- 'deezer', 'tidal', 'qobuz', 'soundcloud'
    service_id      TEXT,
    added_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    metadata_blob   TEXT,
    UNIQUE(artist_id, title)
);

CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist_id);
CREATE INDEX IF NOT EXISTS idx_albums_title ON albums(title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_albums_status ON albums(download_status);
CREATE INDEX IF NOT EXISTS idx_albums_mbid ON albums(mb_albumid);

-- Tracks
CREATE TABLE IF NOT EXISTS tracks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id        INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    track_number    INTEGER,
    disc_number     INTEGER DEFAULT 1,
    duration        REAL,
    artist          TEXT,
    file_path       TEXT,
    file_format     TEXT,          -- 'FLAC', 'MP3', 'AAC', 'ALAC', 'OPUS'
    bitrate         INTEGER,
    sample_rate     INTEGER,
    bit_depth       INTEGER,
    isrc            TEXT,
    mb_recording_id TEXT,
    service_id      TEXT,
    download_status TEXT NOT NULL DEFAULT 'pending',
                    -- 'pending' | 'downloaded' | 'failed' | 'skipped'
    added_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(download_status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_path ON tracks(file_path) WHERE file_path IS NOT NULL;

-- Download log (append-only audit trail)
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

-- Scheduler run log
CREATE TABLE IF NOT EXISTS scheduler_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name        TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    status          TEXT NOT NULL, -- 'running' | 'success' | 'failed'
    message         TEXT,
    albums_found    INTEGER DEFAULT 0,
    tracks_added    INTEGER DEFAULT 0,
    tracks_dled     INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sched_log_job ON scheduler_log(job_name);
```

#### 3.2.3 Design Rationale

- **`metadata_blob`**: Cached JSON from the streaming service API to avoid re-fetching. Contains full API response for the artist/album. Minimizes API calls.
- **`UNIQUE(artist_id, title)`**: Prevents duplicate album entries. Collation `NOCASE` for case-insensitive dedup.
- **`download_log`** is append-only. When upgrading quality, a new entry is inserted; the track's `file_path` is updated. This preserves provenance.
- **`ON DELETE CASCADE`**: Removing an artist cascades to albums, tracks, and download log entries.

### 3.3 Backend Abstraction Layer (`src/rswd/backends/`)

#### 3.3.1 Abstract Base Class

```python
# src/rswd/backends/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class SearchResult:
    service: str               # "deezer", "tidal", etc.
    media_type: str            # "artist", "album", "track", "playlist"
    service_id: str            # ID on the streaming service
    title: str
    artists: tuple[str, ...]
    year: Optional[int] = None
    duration_s: Optional[int] = None
    track_count: Optional[int] = None
    cover_url: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TrackInfo:
    service: str
    service_id: str
    title: str
    artist: str
    album: str
    album_id: str
    track_number: int
    disc_number: int = 1
    duration_s: Optional[float] = None
    isrc: Optional[str] = None
    explicit: bool = False
    file_format: Optional[str] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    bit_depth: Optional[int] = None


@dataclass(frozen=True)
class AlbumInfo:
    service: str
    service_id: str
    title: str
    artist: str
    year: Optional[int] = None
    tracks: tuple[TrackInfo, ...] = ()
    cover_url: Optional[str] = None
    label: Optional[str] = None
    upc: Optional[str] = None
    total_tracks: Optional[int] = None
    total_discs: Optional[int] = None
    explicit: bool = False


@dataclass
class DownloadResult:
    track_info: TrackInfo
    file_path: Path
    success: bool
    error: Optional[str] = None


class SearchDownloadBackend(ABC):
    """Abstract interface for all download backends."""

    @abstractmethod
    def search(
        self, media_type: str, query: str, limit: int = 10
    ) -> list[SearchResult]:
        """Search for artists, albums, or tracks."""
        ...

    @abstractmethod
    def search_artist_discography(
        self, artist_name: str
    ) -> dict[str, list[AlbumInfo]]:
        """Search for an artist and return all their albums grouped by service.
        Returns {service_name: [AlbumInfo, ...]}."""
        ...

    @abstractmethod
    def get_album_info(self, service: str, service_id: str) -> AlbumInfo:
        """Fetch full album metadata including track listing."""
        ...

    @abstractmethod
    def download_album(
        self,
        service: str,
        service_id: str,
        album_info: AlbumInfo,
        output_dir: Path,
        quality: int = 2,
        codec: Optional[str] = None,
    ) -> list[DownloadResult]:
        """Download all tracks in an album.

        The backend is responsible for:
        1. Downloading each track's audio stream
        2. Applying codec conversion if requested
        3. Embedding metadata tags and cover art
        4. Writing files to output_dir with backend's naming convention

        Returns a DownloadResult per track.
        """
        ...

    @abstractmethod
    def login_and_validate(self) -> dict[str, bool]:
        """Test all configured service credentials.
        Returns {service_name: is_valid}."""
        ...
```

#### 3.3.2 StreamripBackend Implementation Strategy

streamrip's library API is the primary reason for choosing it:

```python
# Pseudocode for StreamripBackend.download_album()

import asyncio
from streamrip import Config as RpConfig
from streamrip.rip.main import Main

class StreamripBackend(SearchDownloadBackend):

    def __init__(self, config: dict):
        # Build streamrip Config from our config.toml
        self._rp_config = self._build_rp_config(config)

    def _build_rp_config(self, cfg: dict) -> RpConfig:
        """Map our TOML config to streamrip's ConfigData."""
        rp = RpConfig()  # loads default TOML
        rp.session.downloads.folder = cfg["download_path"]
        rp.session.conversion.enabled = bool(cfg.get("codec"))
        rp.session.conversion.codec = (cfg.get("codec") or "FLAC").upper()
        rp.session.downloads.concurrency = cfg.get("concurrency", 3)
        # Map service credentials
        if cfg.get("services", {}).get("deezer", {}).get("arl"):
            rp.session.deezer.arl = cfg["services"]["deezer"]["arl"]
        if cfg.get("services", {}).get("tidal", {}).get("access_token"):
            rp.session.tidal.access_token = cfg["services"]["tidal"]["access_token"]
            rp.session.tidal.refresh_token = cfg["services"]["tidal"]["refresh_token"]
            rp.session.tidal.user_id = cfg["services"]["tidal"]["user_id"]
            rp.session.tidal.country_code = cfg["services"]["tidal"]["country_code"]
        # ... Qobuz, SoundCloud ...
        return rp

    def download_album(self, service, service_id, album_info, output_dir, quality=2, codec=None):
        async def _download():
            # Temporarily override download folder
            self._rp_config.session.downloads.folder = str(output_dir)
            async with Main(self._rp_config) as main:
                await main.add_by_id(service, "album", service_id)
                await main.resolve()
                await main.rip()
            # Scan output_dir for downloaded files
            return self._scan_output(output_dir, album_info)

        return asyncio.run(_download())
```

**Key integration points with streamrip:**
- `Config.session.downloads.folder` → controls output directory
- `Config.session.conversion` → codec transcoding
- `Config.session.deezer.arl` / `.tidal.*` → credentials
- `Main.add_by_id(source, media_type, id)` → ID-based download (no URL parsing)
- `Main.resolve()` → metadata fetch
- `Main.rip()` → actual download + tagging

**Post-download scan:** After `rip()` completes, we scan `output_dir` for the downloaded files. Since we control `folder`, we can predict the path via streamrip's template. We then:
1. Move files to our final library path (using our `filepaths` templates)
2. Register in the `tracks` table
3. Update `download_log`

#### 3.3.3 OrpheusDLBackend (Secondary)

For users who need Apple Music, Spotify, or YouTube support:

```python
class OrpheusBackend(SearchDownloadBackend):

    def __init__(self, config: dict):
        install_path = config.get("backend", {}).get("orpheusdl", {}).get("install_path", "")
        if install_path:
            sys.path.insert(0, install_path)
        from orpheus.core import Orpheus
        self._orpheus = Orpheus()
        # Load modules based on configured services
        for service in self._get_enabled_services(config):
            self._orpheus.load_module(service)
```

The OrpheusDL integration follows the same `SearchDownloadBackend` interface, mapping our internal API to OrpheusDL's `ModuleInterface` methods (`search`, `get_album_info`, `get_track_download`).

### 3.4 CLI Design (`src/rswd/cli/`)

#### 3.4.1 Command Tree

```
rswd
├── artist
│   ├── add <name> [--service deezer]
│   ├── list [--monitored] [--unmonitored]
│   ├── remove <artist-id>
│   ├── monitor <artist-id>
│   └── unmonitor <artist-id>
├── album
│   ├── search <query> [--service tidal]
│   ├── download <album-id> [--quality 2]
│   └── list [--artist <id>] [--status none|partial|complete]
├── library
│   ├── status                    # Stats: artists, albums, tracks, size
│   ├── scan [--path ./music]     # Import existing files into DB
│   └── prune                     # Remove DB entries for missing files
├── search
│   └── <query>                   # Cross-service search for artists/albums
├── daemon
│   ├── start
│   ├── stop
│   ├── restart
│   └── status
├── config                        # Print current config
└── log [--tail 50]               # Show recent log entries
```

#### 3.4.2 Click Implementation Pattern

```python
# src/rswd/cli/app.py
import click


@click.group()
@click.option("--config", "-c", default=None, help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx, config, verbose):
    """rswd-cli: Automated music library manager.

    Manages artist subscriptions and downloads from streaming services.
    """
    ctx.ensure_object(dict)
    from rswd.config import load_config
    ctx.obj["config"] = load_config(config)  # returns frozen dataclass
    from rswd.db.schema import ensure_schema
    ensure_schema(ctx.obj["config"].core.library_db)
```

```python
# src/rswd/cli/artist.py
@click.group()
def artist():
    """Manage artist subscriptions."""
    pass

@artist.command("add")
@click.argument("name")
@click.option("--service", default=None, help="Service to search (deezer, tidal)")
@click.option("--monitor/--no-monitor", default=True, help="Monitor for new releases")
@click.option("--quality", type=int, default=2, help="Quality tier to monitor for")
@click.pass_context
def artist_add(ctx, name, service, monitor, quality):
    """Add an artist and optionally download their discography."""
    from rswd.library import add_artist
    result = add_artist(ctx.obj["config"], name, service, monitor, quality)
    if result:
        click.echo(f"Added: {result.artist_name} ({result.service})")
        click.echo(f"  Albums found: {result.album_count}")
        click.echo(f"  Downloading discography...")
        # If monitor, scheduler will check for new releases
```

### 3.5 Metadata Subsystem (`src/rswd/metadata/`)

#### 3.5.1 Why a Separate Metadata Layer?

streamrip and OrpheusDL already embed cover art and lyrics from the **streaming service itself** during download. For ~95% of content, no additional metadata fetching is needed — the service provides everything: cover art, artist/album/track names, ISRCs, UPCs, labels, composers, lyrics, and credits.

A separate metadata layer exists for:

| Scenario | Frequency | Solution |
|----------|-----------|----------|
| Service has no lyrics for this track | ~10-15% of tracks | LRCLIB fallback |
| Cover art from service is low-res | ~5% | MusicBrainz CAA → iTunes fallback |
| User wants to cross-reference with MusicBrainz | Configurable | `musicbrainzngs` enrichment |
| User has custom metadata sources | Niche | Plugin system |

**Design decision**: Metadata enrichment is **post-download, optional, and non-blocking**. The download pipeline never waits for metadata enrichment. Enrichment runs as a separate async step after the file is already tagged by streamrip, and only overwrites fields that are empty or explicitly configured for replacement.

#### 3.5.2 Layered Architecture

```
┌────────────────────────────────────────────────────────────┐
│              Layer 0: Embedded (streamrip/OrpheusDL)       │
│  Gets lyrics and cover from the streaming service API       │
│  during download. Mutagen embeds both into audio file.      │
│  Handled by: streamrip's tag_file() / OrpheusDL's tagging() │
├────────────────────────────────────────────────────────────┤
│              Layer 1: LRCLIB (Free, no API key)            │
│  Post-download enrichment for missing lyrics.               │
│  https://lrclib.net/ — open database, synced LRC support.  │
│  Query: track_name + artist_name + album_name + duration   │
├────────────────────────────────────────────────────────────┤
│              Layer 2: Cover Art Fallback Chain             │
│  MusicBrainz Cover Art Archive → iTunes public API          │
│  Only triggered if embedded cover is missing or too small.  │
├────────────────────────────────────────────────────────────┤
│              Layer 3: MusicBrainz Metadata (Optional)      │
│  Populates mb_artistid / mb_albumid / mb_recording_id      │
│  in the database. Uses musicbrainzngs with 1 req/s limit.  │
├────────────────────────────────────────────────────────────┤
│              Layer 4: Plugin System                         │
│  User-provided metadata hooks via entry points.             │
│  Same importlib.metadata pattern as download backends.     │
│  E.g. Musixmatch lyrics, Discogs covers, AcousticBrainz    │
└────────────────────────────────────────────────────────────┘
```

#### 3.5.3 LRCLIB Integration

**Source**: `https://lrclib.net/` — free, open lyrics database. No API key. Supports plain and synced (LRC timestamps) lyrics.

**API surface**:
```
GET /api/get?track_name={track}&artist_name={artist}&album_name={album}&duration={duration}
  → { id, trackName, artistName, albumName, duration, plainLyrics, syncedLyrics, isInstrumental }

GET /api/search?q={query}
  → [{ id, trackName, artistName, albumName, duration, ... }]
```

**Python usage** — no wrapper library needed, direct `httpx`/`requests`:

```python
class LRCLibProvider:
    """Free lyrics provider. No API key. No rate limiting documented."""

    BASE_URL = "https://lrclib.net/api"

    def fetch(
        self,
        track: str,
        artist: str,
        album: str | None = None,
        duration: int | None = None,
    ) -> LyricsResult | None:
        params = {"track_name": track, "artist_name": artist}
        if album:   params["album_name"] = album
        if duration: params["duration"] = duration

        resp = httpx.get(f"{self.BASE_URL}/get", params=params, timeout=10)
        if resp.status_code == 404:
            return None  # not found
        resp.raise_for_status()
        data = resp.json()
        return LyricsResult(
            source="lrclib",
            plain=data.get("plainLyrics"),
            synced=data.get("syncedLyrics"),
            is_instrumental=data.get("isInstrumental", False),
        )

    def embed_in_file(self, file_path: str, lyrics: LyricsResult):
        """Embed lyrics into an audio file via mutagen."""
        audio = mutagen.File(file_path)
        if audio is None:
            return
        if lyrics.synced:
            audio["lyrics"] = lyrics.synced  # format-specific key handled by mutagen
        elif lyrics.plain:
            audio["lyrics"] = lyrics.plain
        audio.save()
```

**Why LRCLIB and not LibreLyrics**: LibreLyrics (April 2026, 18 stars, 3 commits) is too immature to depend on. Its plugin-based architecture is the right idea but the implementation is embryonic. LRCLIB is a stable, simple HTTP API. If LibreLyrics matures, it can be supported as a metadata plugin in Layer 4.

#### 3.5.4 Cover Art Fallback Chain

**Problem**: The streaming service's cover art is almost always adequate (Deezer: 1400x1400, Tidal: 1280x1280, Qobuz: up to 3000x3000). Edge cases:

| Issue | Service | Frequency |
|-------|---------|-----------|
| No cover returned for some tracks | All | ~1% |
| Low-res placeholder image (e.g. Deezer "no cover") | Deezer | ~2% for obscure tracks |
| User wants uniform 3000px covers | Manual preference | Configurable |

**Fallback chain** (only triggered when configured, or when embedded cover is missing/sub-minimum-size):

```
if cover is missing or cover_size < config.min_cover_bytes:
    1. MusicBrainz CAA get_image_front(album_mbid, size=1200)
       Requires mb_albumid (populated by Layer 3)
    2. If no CAA result:
       iTunes public search (GET https://itunes.apple.com/search?term=...)
       → results[0].artworkUrl100 → replace 100x100 with 1200x1200
    3. If no iTunes result:
       Deezer public API (free, no key)
       GET https://api.deezer.com/search/album?q=...
       → album.cover_xl (1000x1000)
```

**Not using sacad**: sacad v3+ is Rust-only (`cargo install sacad`). The Python v2.x branch is archived. Subprocessing a Rust binary adds a build dependency for users. The `coverart-cli` Python library (also mentioned in research) exists but is too niche (700 LOC, 1 contributor). The fallback chain above is 30 lines of Python and covers the same sources.

#### 3.5.5 MusicBrainz Enrichment (Layer 3)

**Purpose**: Populate `mb_artistid`, `mb_albumid`, `mb_recording_id`, `mb_release_groupid` in the SQLite database. These enable cross-referencing across services and provide stable canonical identifiers.

**When triggered**:
- After download completes (non-blocking background task)
- Only if `metadata.musicbrainz = true` in config

**Lookup strategy** (ordered by precision):

```
For each downloaded track:
  1. If track has ISRC from service (most do):
     → musicbrainzngs.get_recordings_by_isrc(isrc)
     → extract mb_recordingid, mb_albumid, mb_artistid
  2. If album has UPC/barcode from service:
     → search_releases(query=barcode)
     → extract mb_albumid
  3. Fallback: text search
     → search_recordings(recording=title, artist=artist)
     → pick highest-scoring result
```

**Rate limiting**: 1 req/s enforced by `musicbrainzngs.set_rate_limit(1.0)`. For a 12-track album, enrichment takes ~15 seconds. Acceptable for a background task.

**Why not always**: MusicBrainz requires rate limiting and can 503. It's optional because the streaming service's metadata is already sufficient for most use cases. The MBIDs are only needed for cross-service dedup and cover art fallback.

#### 3.5.6 Metadata Aggregator (Coordinator)

The `MetadataAggregator` coordinates all enrichment layers:

```python
class MetadataAggregator:
    """Orchestrates post-download metadata enrichment."""

    def __init__(self, config):
        self.lrclib = LRCLibProvider()
        self.cover_fallback = CoverFallbackChain()
        self.musicbrainz = MusicBrainzEnricher() if config.metadata.musicbrainz else None
        self.plugins = discover_metadata_plugins()  # Layer 4

    async def enrich_track(
        self,
        track_path: str,
        track_meta: dict,      # title, artist, album, isrc, etc.
        album_mbid: str | None,
    ) -> EnrichmentResult:
        """Run all enrichment steps. Each step is independent and non-blocking."""
        result = EnrichmentResult()

        # Layer 1: Missing lyrics
        if not self._has_lyrics_embedded(track_path):
            lyrics = await self.lrclib.fetch(
                track=track_meta["title"],
                artist=track_meta["artist"],
                album=track_meta.get("album"),
                duration=track_meta.get("duration_s"),
            )
            if lyrics:
                self.lrclib.embed_in_file(track_path, lyrics)
                result.lyrics_found = True

        # Layer 2: Missing or undersized cover
        cover_size = self._embedded_cover_size(track_path)
        if cover_size is None or cover_size < self.config.min_cover_bytes:
            cover_data = await self.cover_fallback.fetch(album_mbid, track_meta)
            if cover_data:
                self._embed_cover(track_path, cover_data)
                result.cover_replaced = True

        # Layer 3: MusicBrainz IDs (async, rate-limited)
        if self.musicbrainz and not track_meta.get("mb_recording_id"):
            mb_ids = await self.musicbrainz.lookup(track_meta)
            if mb_ids:
                result.mb_ids = mb_ids

        # Layer 4: Plugins
        for plugin in self.plugins:
            try:
                await plugin.process(track_path, track_meta)
            except Exception:
                logger.warning(f"Metadata plugin {plugin.name} failed", exc_info=True)

        return result
```

#### 3.5.7 Config Options for Metadata

```toml
[metadata]
# Cover art
embed_cover = true              # Embed cover art in audio file tags
cover_size = 1400               # Max width for embedded cover
min_cover_bytes = 30000         # If embedded cover is smaller, try to replace
cover_fallback = true           # Enable MusicBrainz → iTunes → Deezer fallback

[metadata.lyrics]
embed = true                    # Embed lyrics in audio file tags
prefer_synced = true            # Prefer synced (timestamped) lyrics over plain
providers = ["lrclib"]          # Ordered list: lrclib, musixmatch (plugin)

[metadata.musicbrainz]
enrichment = false              # Populate MBIDs in database (requires musicbrainzngs)
rate_limit = 1.0                # Requests per second to MusicBrainz API

[metadata.replaygain]
enabled = false                 # Calculate EBU R128 loudness tags (requires ffmpeg)
mode = "album"                  # "track" | "album" | "both"

[metadata.acoustid]
enabled = false                 # Audio fingerprinting for library scan
api_key = ""                    # Get at https://acoustid.org/ (free)
```

#### 3.5.8 Summary: What the Backend Provides vs. What We Add

| Metadata | streamrip/OrpheusDL provides | rswd-cli adds |
|----------|------------------------------|-----------------|
| Cover art (embedded) | ✅ From streaming service | Fallback chain for edge cases |
| Cover art (external file) | ✅ Configurable | — |
| Lyrics (embedded) | ✅ From streaming service | LRCLIB fallback for missing |
| Synced lyrics (embedded) | ✅ If service provides | LRCLIB upgrade path |

| Enhanced LRC (word-level karaoke) | ❌ | Plugin (OrpheusDL only in v1.0) |
| Artist/album/track names | ✅ | — |
| ISRC | ✅ Most services | — |
| UPC/barcode | ✅ Some services | — |
| MusicBrainz IDs (mb_*) | ❌ | `musicbrainzngs` enrichment |
| Composer credits | ✅ Tidal/Deezer | — |
| Genre | ✅ From service | — |
| ReplayGain 2.0 (EBU R128) | ❌ | ffmpeg ebur128 + mutagen |
| AcoustID fingerprint | ❌ | `pyacoustid` for library scan |
| Custom tags | ❌ | Plugin system |

The rule: **If the streaming service provides it, we use it. We only add enrichment for what the service doesn't provide, or as opt-in cross-referencing.**

#### 3.5.9 ReplayGain 2.0 / EBU R128 Loudness Normalization

**Problem**: Neither streamrip nor OrpheusDL apply ReplayGain tags. This means album-to-album volume varies wildly depending on mastering. Players like Plexamp, foobar2000, and VLC can use ReplayGain tags to normalize playback volume without modifying audio data.

**What ReplayGain provides:**
| Tag | Description | Example |
|-----|-------------|---------|
| `REPLAYGAIN_TRACK_GAIN` | Per-track volume adjustment | `-6.53 dB` |
| `REPLAYGAIN_TRACK_PEAAK` | Per-track peak sample | `0.645012` |
| `REPLAYGAIN_ALBUM_GAIN` | Album-wide volume adjustment | `-7.12 dB` |
| `REPLAYGAIN_ALBUM_PEAK` | Album-wide peak sample | `0.654321` |
| `REPLAYGAIN_REFERENCE_LOUDNESS` | Reference level for measurement | `-18.0 LUFS` |
| `REPLAYGAIN_ALGORITHM` | Algorithm used | `ITU-R BS.1770-4` |

**Implementation**: Use `regainer` as a reference implementation pattern — NOT as a dependency (it has no pip package, it's a single script). Extract the core logic:

```
ffmpeg -i <file> -filter_complex ebur128=framelog=verbose:peak=true[out] -map [out] -f null -
    → Parse stderr for I: <loudness> LUFS and Peak: <peak> dBFS
    → Calculate gain = -18.0 LUFS - measured_loudness  (ReplayGain 2.0 reference)
    → Write tags via mutagen
```

**Implementation plan** (`src/rswd/metadata/replaygain.py`):

```python
import asyncio
import re
import mutagen


class ReplayGainCalculator:
    """Calculates and writes ReplayGain 2.0 tags using ffmpeg's ebur128 filter.

    Depends only on ffmpeg (already required by streamrip) and mutagen.
    """

    RG_REFERENCE = -18.0  # LUFS (ReplayGain 2.0 standard)

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg = ffmpeg_path

    async def measure_track(self, file_path: str) -> tuple[float, float]:
        """Measure loudness and peak of a single track.

        Returns: (loudness_LUFS, peak_dBFS)
        """
        cmd = [
            self.ffmpeg, "-nostats", "-nostdin", "-hide_banner", "-vn",
            "-i", file_path,
            "-filter_complex", "ebur128=framelog=verbose:peak=true[out]",
            "-map", "[out]", "-f", "null", "-",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        loudness = peak = 0.0
        i_re = re.compile(rb"^\s+I:\s+(-?\d+\.\d+) LUFS$", re.M)
        p_re = re.compile(rb"^\s+Peak:\s+(-?\d+\.\d+) dBFS$", re.M)
        stdout, stderr = await proc.communicate()
        for match in i_re.finditer(stderr):
            loudness = float(match.group(1))
        for match in p_re.finditer(stderr):
            peak = float(match.group(1))
        return loudness, peak

    def write_track_gain(self, file_path: str, loudness: float, peak: float):
        """Write ReplayGain 2.0 tags for a single track."""
        gain = self.RG_REFERENCE - loudness
        audio = mutagen.File(file_path)
        if audio is None:
            return
        tags = audio.tags
        if isinstance(tags, mutagen.id3.ID3):
            # MP3: Use TXXX frames (foobar2000 compatible)
            from mutagen.id3 import TXXX
            tags.delall("TXXX:REPLAYGAIN_TRACK_GAIN")
            tags.delall("TXXX:REPLAYGAIN_TRACK_PEAK")
            tags.settext("TXXX:REPLAYGAIN_TRACK_GAIN", f"{gain:.2f} dB")
            tags.settext("TXXX:REPLAYGAIN_TRACK_PEAK", f"{peak:.6f}")
            tags.delall("TXXX:REPLAYGAIN_REFERENCE_LOUDNESS")
            tags.settext("TXXX:REPLAYGAIN_REFERENCE_LOUDNESS", f"{self.RG_REFERENCE:.1f} LUFS")
        else:
            # FLAC, Ogg, M4A: Vorbis-style tags
            tags["REPLAYGAIN_TRACK_GAIN"] = f"{gain:.2f} dB"
            tags["REPLAYGAIN_TRACK_PEAK"] = f"{peak:.6f}"
            tags["REPLAYGAIN_REFERENCE_LOUDNESS"] = f"{self.RG_REFERENCE:.1f} LUFS"
        audio.save()

    async def measure_album(
        self, file_paths: list[str]
    ) -> tuple[float, float]:
        """Measure album loudness by concatenating all tracks."""
        cmd = [self.ffmpeg, "-nostats", "-nostdin", "-hide_banner", "-vn"]
        for fp in file_paths:
            cmd.extend(["-i", fp])
        cmd.extend([
            "-filter_complex",
            f"concat=n={len(file_paths)}:v=0:a=1,ebur128=framelog=verbose:peak=none[out]",
            "-map", "[out]", "-f", "null", "-",
        ])
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        match = re.search(rb"^\s+I:\s+(-?\d+\.\d+) LUFS$", stderr, re.M)
        if not match:
            return (0.0, 0.0)
        album_loudness = float(match.group(1))
        album_gain = self.RG_REFERENCE - album_loudness
        return (album_gain, 0.0)  # peak not available for concatenated stream

    def write_album_gain(self, file_paths: list[str], album_gain: float):
        """Write album ReplayGain tags to all files."""
        for fp in file_paths:
            audio = mutagen.File(fp)
            if audio is None:
                continue
            tags = audio.tags
            if isinstance(tags, mutagen.id3.ID3):
                from mutagen.id3 import TXXX
                tags.delall("TXXX:REPLAYGAIN_ALBUM_GAIN")
                tags.settext("TXXX:REPLAYGAIN_ALBUM_GAIN", f"{album_gain:.2f} dB")
            else:
                tags["REPLAYGAIN_ALBUM_GAIN"] = f"{album_gain:.2f} dB"
            audio.save()
```

**When to run**: Post-download, after files are moved to the library. Configurable:

```toml
[metadata.replaygain]
enabled = false                  # Off by default (requires ffmpeg)
mode = "album"                   # "track", "album", "both"
```

**Why not rgain3**: `rgain3` depends on GStreamer (`gi.repository`), which adds a complex native dependency chain on all platforms. Using `ffmpeg`'s `ebur128` filter is zero-additional-dependency (user already needs ffmpeg for streamrip codec conversion) and is the same backend that `regainer` uses internally.

#### 3.5.10 AcoustID Audio Fingerprinting

**Purpose**: For the `library scan` command — identify unknown audio files by generating a Chromaprint fingerprint and querying AcoustID. Returns MusicBrainz recording IDs, which we can use to look up artist/album/track metadata.

**Use case**: User has a directory of existing music files. `rswd library scan --path ./unknown_music` fingerprints each file, queries AcoustID, and matches results to the local library or creates placeholder entries.

**Dependency**: `pip install pyacoustid` (by the `beetbox` team, battle-tested in beets since 2010). Requires the Chromaprint C library, which can be:
- Installed via system package manager (`apt install libchromaprint`, `brew install chromaprint`)
- Used via the `fpcalc` binary (downloadable from AcoustID website)
- Bundled with Python wheels on some platforms

```python
# src/rswd/metadata/acoustid.py

import acoustid
from pathlib import Path
from typing import Optional


class AcoustIDMatcher:
    """Identifies audio files via Chromaprint/AcoustID fingerprinting."""

    def __init__(self, api_key: str):
        # API key from https://acoustid.org/ (free, one-time registration)
        self.api_key = api_key

    def identify(self, file_path: str) -> list[dict]:
        """Fingerprint a file and return AcoustID results.

        Returns list of {score, recording_id, title, artist} tuples.
        """
        try:
            results = list(acoustid.match(self.api_key, file_path))
        except acoustid.AcoustidError as e:
            logger.warning(f"AcoustID lookup failed for {file_path}: {e}")
            return []

        return [
            {
                "score": score,           # 0.0 - 1.0 confidence
                "mb_recording_id": rid,
                "title": title,
                "artist": artist,
            }
            for score, rid, title, artist in results
        ]
```

**Rate limiting**: `pyacoustid` internally enforces 3 req/s. No additional throttling needed.

**Config**:
```toml
[metadata.acoustid]
enabled = false
api_key = ""                 # Required. Get from https://acoustid.org/
```

**Future integration**: AcoustID results can feed into `library scan` to auto-populate track metadata for files where tags are missing or inconsistent.

#### 3.5.11 Enhanced LRC / Word-Level Karaoke Lyrics

OrpheusDL via its Musixmatch module already supports `enable_enhanced_lyrics: true` which saves word-by-word Enhanced LRC files. For streamrip-based installations (our default), this can be added as a post-download step using the `lrxy` library or a direct implementation:

```python
# Enhanced LRC format:
# [00:13.15]<00:13.15>Oh <00:13.55>it <00:13.80>was <00:14.20>the <00:14.50>night
# [00:16.80]<00:16.80>Things <00:17.10>were <00:17.40>different
```

**Status**: Enhanced LRC (word-level) is a niche feature. LRCLIB doesn't provide it (line-level only). Musixmatch provides it via a paid/proprietary API. Apple Music provides it via TTML format (converted to Enhanced LRC by tools like `eepyyyy/enhanced-lrc`). This is **not implemented in v1.0** but the plugin architecture supports it — a third-party plugin can enhance the enrichment pipeline.

#### 3.5.13 Post-Download Enrichment Pipeline (Complete)

```
Download completes (via streamrip)
    │
    ▼
┌──────────────────────────────────────────────────┐
│ Post-Process Pipeline (sequential, non-blocking)  │
├──────────────────────────────────────────────────┤
│  1. Verify file integrity (size > 0, mutagen opens)│
│  2. Move file to library path + rename            │
│  3. SHA256 checksum → download_log                │
│  4. Register in tracks table (file_path, format,   │
│     bitrate, sample_rate, bit_depth)              │
│  5. [Optional] LRCLIB lyrics enrichment           │
│  6. [Optional] ReplayGain calculation & tagging   │
│  7. [Optional] MusicBrainz ID enrichment           │
│     (runs as background deferred task)            │
│  8. [Plugin] Third-party hooks                     │
└──────────────────────────────────────────────────┘

Steps 5-8 run **after** the file is safely in the library. The CLI command returns immediately after step 4. Enrichment is async and logged independently. Failure in steps 5-8 never blocks the download pipeline.

### 3.6 Scheduler (`src/rswd/scheduler/jobs.py`)

#### 3.5.1 Architecture

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.interval import IntervalTrigger
```

**Job store:** SQLite via SQLAlchemy (`sqlite:///jobs.db`). This persists scheduled jobs across restarts so missed checks are recovered (with `coalesce=True`).

#### 3.5.2 Job Definition

```python
def check_new_releases(config_path: str):
    """Main monitoring job. Runs on the configured interval.

    Flow:
    1. Load config and connect to DB
    2. Query all monitored artists
    3. For each artist, search streaming services for albums not in DB
    4. For each new album:
       a. Insert into albums table (download_status='none')
       b. Insert tracks into tracks table (download_status='pending')
       c. Trigger download via backend
    5. Log results
    """
    config = load_config(config_path)
    backend = get_backend(config)
    repo = Repository(config.core.library_db)

    monitored_artists = repo.get_monitored_artists()
    for artist in monitored_artists:
        # Search services for this artist
        all_albums = backend.search_artist_discography(artist.name)
        for service, albums in all_albums.items():
            for album in albums:
                if not repo.album_exists(artist.id, album.title, album.year):
                    # New album found
                    album_id = repo.insert_album(
                        artist_id=artist.id,
                        title=album.title,
                        year=album.year,
                        service=service,
                        service_id=album.service_id,
                    )
                    # Queue download
                    _download_album(repo, backend, album_id, album, config)
```

#### 3.5.3 Scheduling

```python
def start_daemon(config):
    scheduler = BackgroundScheduler(
        jobstores={
            "default": SQLAlchemyJobStore(url=f"sqlite:///{config.core.jobs_db}")
        },
        job_defaults={
            "coalesce": True,         # Merge missed runs
            "max_instances": 1,       # No concurrent runs of same job
            "misfire_grace_time": 3600,  # 1 hour grace
        },
    )
    scheduler.add_job(
        check_new_releases,
        trigger=IntervalTrigger(hours=config.daemon.check_interval_hours),
        args=[config_path],
        id="check_new_releases",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
```

### 3.6 File Management

#### 3.6.1 Naming Convention

```python
# Template variables resolved at download time:
album_folder = "{albumartist}/{album} ({year})"
track_file   = "{tracknum:02d}. {artist} - {title}{ext}"

# Example output:
# ~/music/Radiohead/OK Computer (1997)/
#   01. Radiohead - Airbag.flac
#   02. Radiohead - Paranoid Android.flac
#   ...
```

Templates use Python `str.format()` with sanitized values (illegal filesystem chars stripped).

#### 3.6.2 Post-Download Flow

```
Backend downloads to:          download_path/temp/album_id/
                                     ├── track01.flac  (raw from streamrip)
                                     ├── track02.flac
                                     └── cover.jpg

Post-process (rswd-cli):
  1. Verify each downloaded file (size > 0, valid audio header)
  2. Compute SHA256 for download_log
  3. Move to: download_path/{album_folder}/{track_file}
  4. Remove temp directory
  5. Register in tracks table (file_path, file_format, bitrate, etc.)
  6. Insert download_log entry
  7. Update album.download_status = 'complete'
```

---

## 4. Data Flow (End-to-End)

### 4.1 Artist Addition Flow

```
User: rswd artist add "Radiohead"
                │
                ▼
    ┌───────────────────────┐
    │ parse artist name     │
    └────────┬──────────────┘
             │
             ▼
    ┌───────────────────────┐
    │ search backends       │  streamrip.backend.search("artist", "Radiohead")
    │ for artist            │  → DeezerArtistSearch / TidalArtistSearch
    └────────┬──────────────┘
             │
             ▼  result: [SearchResult(service="deezer", service_id="123",
             │            title="Radiohead", ...),
             │           SearchResult(service="tidal", service_id="456", ...)]
             │
             ▼
    ┌───────────────────────┐
    │ pick best result      │  Prefer configured primary service, or user
    │ (or prompt if         │  explicitly selected --service
    │  multiple)            │
    └────────┬──────────────┘
             │
             ▼
    ┌───────────────────────┐
    │ fetch discography     │  backend.search_artist_discography("Radiohead")
    │                       │  → fetches all albums from Deezer/Tidal
    │                       │  → AlbumInfo(album, single, ep, compilation)
    └────────┬──────────────┘
             │
             ▼
    ┌───────────────────────┐
    │ insert into DB        │
    │  artists: name, mb_id │
    │  albums: title,year,  │
    │          tracks       │
    │  quality_tier=2       │
    └────────┬──────────────┘
             │
             ▼
    ┌───────────────────────┐
    │ download discography  │  backend.download_album(...) for each album
    │                       │  → streamrip downloads, tags, renames
    │                       │  → post-process moves to library, registers
    └────────┬──────────────┘
             │
             ▼
    ┌───────────────────────┐
    │ mark as monitored     │  scheduler will check for new albums
    └───────────────────────┘
```

### 4.2 Monitoring Flow (Scheduled Job)

```
APScheduler: check_new_releases()
                │
                ▼
    ┌───────────────────────┐
    │ SELECT * FROM artists │
    │ WHERE is_monitored=1  │
    └────────┬──────────────┘
             │ for each artist
             ▼
    ┌───────────────────────┐
    │ search artist albums  │  backend.search_artist_discography(artist.name)
    │ on all services       │  → list of AlbumInfo from each service
    └────────┬──────────────┘
             │
             ▼
    ┌───────────────────────┐
    │ cross-reference with  │  SELECT title, year FROM albums
    │ local DB              │  WHERE artist_id=?
    └────────┬──────────────┘
             │ albums not in DB = NEW
             ▼
    ┌───────────────────────┐
    │ insert new albums     │
    │ + tracks into DB      │
    └────────┬──────────────┘
             │
             ▼
    ┌───────────────────────┐
    │ download each         │  backend.download_album(...)
    │ new album             │
    └────────┬──────────────┘
             │
             ▼
    ┌───────────────────────┐
    │ update scheduler_log  │  albums_found, tracks_dled
    └───────────────────────┘
```

---

## 5. Integration Points

### 5.1 streamrip Integration

| Concern | streamrip Class/Method | Our Wrapper |
|---------|----------------------|-------------|
| Config loading | `Config(path)` | `StreamripBackend._build_rp_config()` |
| Auth | `Config.session.{service}.{cred}` fields | Mapped from our TOML in `__init__` |
| Search | `Client.search(media_type, query, limit)` | `StreamripBackend.search()` wraps `main.search_take_first` or direct client call |
| Album metadata | `Client.get_metadata(id, "album")` → dict | `StreamripBackend.get_album_info()` parses dict into `AlbumInfo` |
| Download | `Main.add_by_id()` → `resolve()` → `rip()` | `StreamripBackend.download_album()` wraps with context manager |
| File placement | `Config.session.downloads.folder` | Override per-download to our temp dir |
| Quality | `Config.session.{service}.quality` | Mapped from our `quality` int (0-4) |
| Codec conversion | `Config.session.conversion.{codec}` | Mapped from our `codec` string |

### 5.2 MusicBrainz Integration (Optional Enrichment)

| Concern | musicbrainzngs Method | When Called |
|---------|-----------------------|-------------|
| Artist ID lookup | `search_artists(artist=name)` | On artist add, if service doesn't provide MBID |
| Discography check | `browse_release_groups(artist=mbid)` | Optional cross-reference with streaming results |
| Release details | `get_release_by_id(mbid, includes=["recordings","labels"])` | Populate `mb_*` fields in DB |
| ISRC resolution | `get_recording_by_id(mbid, includes=["isrcs"])` | Fill missing ISRCs in tracks table |
| Cover art | `get_image_front(release_mbid, size="500")` | Fallback if service cover isn't available |

**Rate limiting:** 1 req/sec. Use `musicbrainzngs.set_rate_limit(1.0)`. Cache MBIDs in DB to avoid repeat lookups.

### 5.3 Mutagen Tagging (via streamrip)

Not directly integrated — streamrip's `tag_file()` function handles all tagging internally. Our only concern is:
1. Ensuring streamrip's `metadata.exclude` list doesn't remove tags we want
2. Adding custom tags post-download if needed

---

## 6. Plugin / Extensibility Strategy

### 6.1 Download Backend Plugins

The `SearchDownloadBackend` ABC is the extension point. To add a new backend:

```python
from rswd.backends.base import SearchDownloadBackend, SearchResult, AlbumInfo

class MyCustomBackend(SearchDownloadBackend):
    def search(self, media_type, query, limit=10):
        ...  # implement
    def search_artist_discography(self, artist_name):
        ...
    def get_album_info(self, service, service_id):
        ...
    def download_album(self, service, service_id, album_info, output_dir, quality=2, codec=None):
        ...
    def login_and_validate(self):
        ...
```

Register in `pyproject.toml`:

```toml
[project.entry-points."rswd.backends"]
mybackend = "my_package:MyCustomBackend"
```

Discovery:

```python
from importlib.metadata import entry_points
backends = entry_points(group="rswd.backends")
for ep in backends:
    cls = ep.load()
    register(ep.name, cls)
```

### 6.2 Event Hooks (Future)

Post-download hooks via entry points allow external tools to process files:

```toml
[project.entry-points."rswd.hooks.post_download"]
replaygain = "my_plugin:replaygain_hook"
```

---

## 7. Requirements & Dependencies

### 7.1 Python Dependencies

```
# Required (hard dependencies)
click>=8.1                          # CLI framework
rich>=13.0                          # Terminal formatting, tables, progress bars
apscheduler>=3.10,<4.0              # Job scheduling
tomli>=2.0                          # TOML config parsing (stdlib 3.11)

# Download backend (at least one required)
streamrip>=1.5                      # Primary backend

# Post-download metadata enrichment
mutagen>=1.47                       # Tagging (also used internally by streamrip)

# Optional enrichment modules
musicbrainzngs>=0.7.1               # MusicBrainz MBID enrichment
pyacoustid>=1.3                     # AcoustID fingerprinting (library scan)
httpx>=0.27                         # LRCLIB API client (or use stdlib urllib)
```

### 7.2 External Binaries

```
ffmpeg (required by streamrip for codec conversion; also used for ReplayGain)
chromaprint / fpcalc (required by pyacoustid for fingerprinting)
```

### 7.3 Service Requirements

| Service | Requires | streamrip Support | OrpheusDL Support |
|---------|----------|-------------------|-------------------|
| Deezer | ARL cookie (free) or Premium | ✅ | ✅ |
| Tidal | HiFi subscription | ✅ | ✅ |
| Qobuz | Sublime subscription | ✅ | ✅ |
| SoundCloud | Free account | ✅ | ✅ |
| Apple Music | Subscription | ❌ | ✅ |
| Spotify | Premium | ❌ | ✅ |
| YouTube | Free | ❌ | ✅ |

---

## 8. Error Handling Strategy

### 8.1 Failure Classification

```
DownloadFailure
├── ServiceError           # Service is down, rate-limited, or returned 5xx
├── AuthError              # Credentials expired, invalid, or revoked
├── GeoRestrictedError     # Content not available in user's region
├── QualityUnavailable     # Requested quality not available for this track
├── CorruptedDownload      # File size 0, invalid header, checksum mismatch
└── FilesystemError        # Disk full, permission denied, path too long
```

### 8.2 Retry Policy

| Error Type | Immediate Retry | Delayed Retry | Max Attempts |
|-----------|----------------|---------------|-------------|
| ServiceError | No | Yes (5 min, then 30 min) | 3 |
| AuthError | No | Yes (notify user) | 1 (manual fix needed) |
| GeoRestrictedError | No | No | 0 (skip permanently) |
| QualityUnavailable | Yes (fallback to lower quality) | No | 1 |
| CorruptedDownload | No | Yes (full retry) | 2 |
| FilesystemError | No | No | 0 (fix path/permissions) |

---

## 9. Testing Strategy

### 9.1 Framework & Structure

```
Framework: pytest >= 8.0
Coverage: pytest-cov (threshold: 80%)
Mocking: pytest-mock + unittest.mock
Fixtures: conftest.py per module
CI: GitHub Actions (Ubuntu 22.04 + Windows Server 2022)
```

**File layout:**
```
tests/
├── conftest.py                # Global fixtures: temp_dir, test_config, test_db
├── test_db/
│   ├── conftest.py            # DB fixtures: populated_schema, sample_artist
│   ├── test_schema.py         # DDL execution, migration, rollback
│   ├── test_models.py         # Dataclass construction, validation
│   └── test_repository.py     # CRUD: insert, query, update, delete, cascade
├── test_backends/
│   ├── conftest.py            # Mocked streamrip fixtures
│   ├── test_base.py           # ABC contract enforcement (abstractmethod checks)
│   ├── test_streamrip.py      # Unit tests with mocked streamrip internals
│   ├── fixtures/
│   │   ├── search_results.json     # Pre-recorded API responses
│   │   ├── album_info.json
│   │   └── track_info.json
│   └── cassettes/                  # vcr.py recorded HTTP interactions (future)
├── test_cli/
│   ├── conftest.py            # CliRunner fixtures
│   ├── test_artist.py         # artist add|list|remove|monitor
│   ├── test_album.py          # album search|download|list
│   ├── test_library.py        # library status|scan
│   └── test_daemon.py         # daemon start|stop (smoke tests)
├── test_metadata/
│   ├── conftest.py
│   ├── test_lrclib.py         # LRCLIB API client (mocked HTTP)
│   ├── test_musicbrainz.py    # musicbrainzngs wrapper (mocked)
│   ├── test_replaygain.py     # ffmpeg ebur128 parsing (subprocess mocked)
│   └── test_acoustid.py       # pyacoustid wrapper (mocked)
├── test_scheduler/
│   └── test_jobs.py           # check_new_releases with mocked backend
├── test_config.py             # TOML loading, validation, merge
└── test_util.py               # sanitization, normalization, helpers
```

### 9.2 Mocking Strategy

**Streaming service APIs** — never hit real services in unit tests. Two approaches:

| Approach | Tool | When | Pro |
|----------|------|------|-----|
| Record/Replay | `vcr.py` | Integration tests | Real HTTP traffic, replayed |
| Manual mock | `unittest.mock.patch` | Unit tests | No network dependency |

**streamrip backend mocking:**

```python
# tests/test_backends/conftest.py
@pytest.fixture
def mock_streamrip_main(mocker):
    """Mock streamrip's Main context manager to return canned data."""
    mock_main = mocker.AsyncMock()
    mock_main.add_by_id = mocker.AsyncMock()
    mock_main.resolve = mocker.AsyncMock()
    mock_main.rip = mocker.AsyncMock()
    # Return canned AlbumInfo when add_by_id is called
    mock_main.add_by_id.side_effect = lambda svc, typ, sid: None
    mocker.patch(
        "streamrip.rip.main.Main",
        return_value=mocker.AsyncMock(
            __aenter__=mocker.AsyncMock(return_value=mock_main),
            __aexit__=mocker.AsyncMock(),
        ),
    )
    return mock_main
```

**ffmpeg ReplayGain mocking:**

```python
# tests/test_metadata/test_replaygain.py
@pytest.fixture
def mock_ffmpeg_ebur128(mocker):
    """Mock subprocess so we don't need ffmpeg in tests."""
    mock_proc = mocker.AsyncMock()
    mock_proc.communicate = mocker.AsyncMock(
        return_value=(b"", b"  I: -14.53 LUFS\n  Peak: -0.31 dBFS\n")
    )
    mocker.patch(
        "asyncio.create_subprocess_exec",
        return_value=mock_proc,
    )
```

**LRCLIB mocking:**

```python
@pytest.fixture
def mock_lrclib_response(httpx_mock):
    """Mock httpx to return canned LRCLIB response without network."""
    httpx_mock.add_response(
        url=re.compile(r"https://lrclib\.net/api/get\?.*"),
        json={
            "id": 12345,
            "trackName": "Paranoid Android",
            "artistName": "Radiohead",
            "albumName": "OK Computer",
            "duration": 383,
            "plainLyrics": "Please could you stop the noise...\n",
            "syncedLyrics": "[00:12.00]Please could you stop the noise...\n",
            "isInstrumental": False,
        },
    )
```

### 9.3 Test Matrix

| Test Category | Runs per PR | Coverage Target | Notes |
|--------------|------------|----------------|-------|
| Unit (DB, config, CLI) | ✅ Always | 90%+ | No network, no native deps |
| Backend (mocked streamrip) | ✅ Always | 85%+ | Canned API responses |
| Metadata (mocked HTTP) | ✅ Always | 80%+ | LRCLIB + MusicBrainz mocked |
| Integration (real streamrip) | 🟡 Nightly | — | Requires credentials, skipped if missing |
| ReplayGain (real ffmpeg) | 🟡 Nightly | — | Skipped if ffmpeg not in PATH |
| AcoustID (real fpcalc) | 🟡 Nightly | — | Skipped if chromaprint missing |

### 9.4 CI Configuration

```yaml
# .github/workflows/test.yml
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-22.04, windows-2022]
        python: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: pip install .[dev]
      - run: pip install pytest pytest-cov pytest-httpx pytest-asyncio
      - run: pytest --cov=rswd --cov-report=xml --cov-fail-under=80
      - uses: codecov/codecov-action@v4
```

---

## 10. Security & Credential Management

### 10.1 Threat Model

| Threat | Impact | Likelihood | Mitigation |
|--------|--------|------------|------------|
| Config file read by unauthorized user | Streaming account compromise | Medium (shared machine) | File permissions + keyring opt-in |
| Token logged in plaintext | Account compromise | Low | Redact tokens in log output |
| .toml committed to git | Credential leak | Medium | .gitignore config, `init` command warns |
| Dependency supply chain | RCE via malicious package | Low | Lockfile, dependabot, pinned hashes |

### 10.2 Credential Storage

**Default: plaintext TOML** at `~/.config/rswd/config.toml` with `0600` permissions.

```
~/.config/rswd/
├── config.toml       # 0600 (user-read only)
├── library.db        # 0600
├── jobs.db           # 0600
└── log/              # 0700
    └── rswd.log    # 0600
```

**Opt-in: system keyring** via the `keyring` library:

```python
# src/rswd/config.py
import os
import stat
import keyring

SERVICE_NAME = "rswd-cli"

def _load_credentials(config: ConfigData) -> ConfigData:
    """Attempt to load credentials from system keyring.
    Falls back to config.toml values if keyring unavailable."""
    for svc in ["deezer", "tidal", "qobuz", "soundcloud"]:
        creds = getattr(config.services, svc, {})
        for field in creds:
            keyring_val = keyring.get_password(
                f"{SERVICE_NAME}.{svc}", field
            )
            if keyring_val:
                setattr(creds, field, keyring_val)
    return config

def save_credential_to_keyring(service: str, field: str, value: str):
    """Store a credential in the OS keyring."""
    keyring.set_password(f"{SERVICE_NAME}.{service}", field, value)

def clear_credential_from_config(service: str, field: str):
    """After storing in keyring, blank the value in config.toml."""
    # Rewrite config file with field set to ""
```

**Keyring backends by platform:**
| Platform | Backend | Persistence |
|----------|---------|-------------|
| Linux | Secret Service (GNOME Keyring / KDE Wallet) | Login session |
| macOS | Keychain | Encrypted, login-unlocked |
| Windows | Windows Credential Manager | Encrypted, user-bound |

### 10.3 Secret Redaction in Logs

```python
# src/rswd/config.py
import re

SENSITIVE_PATTERNS = [
    (r'arl\s*=\s*"[^"]+"', 'arl="<redacted>"'),
    (r'password_or_token\s*=\s*"[^"]+"', 'password_or_token="<redacted>"'),
    (r'client_secret\s*=\s*"[^"]+"', 'client_secret="<redacted>"'),
    (r'access_token\s*=\s*"[^"]+"', 'access_token="<redacted>"'),
    (r'refresh_token\s*=\s*"[^"]+"', 'refresh_token="<redacted>"'),
]

def redact_sensitive(value: str) -> str:
    for pattern, replacement in SENSITIVE_PATTERNS:
        value = re.sub(pattern, replacement, value)
    return value
```

### 10.4 Permissions Enforcement

```python
def ensure_config_permissions(path: Path):
    """Set config file to 0600 on Unix."""
    if os.name != "nt":  # Windows doesn't have POSIX permissions
        current = stat.S_IMODE(path.stat().st_mode)
        if current & 0o077:  # group/other have any permissions
            path.chmod(0o600)
            logger.warning("Config file had loose permissions, tightened to 0600")
```

---

## 11. Platform Compatibility

### 11.1 Windows

| Concern | Problem | Mitigation |
|---------|---------|------------|
| MAX_PATH (260 chars) | `{albumartist}/{album} ({year})/{tracknum}. {artist} - {title}.flac` can exceed 260 with deep paths | Use `\\?\` prefix for all file operations. Validate path length before write |
| File locking | streamrip may hold file handle during tagging | Retry with backoff on `PermissionError`. Use `shutil.move` not `os.rename` across volumes |
| Line endings | `.lrc` files written with `\n` would display incorrectly in Notepad | Ensure `open(..., encoding="utf-8")` — irrelevant since we removed sidecars |
| Path separators | Hardcoded `/` in templates | Always use `pathlib.Path` for path arithmetic, never string concatenation |
| Win32 service | `rswd daemon start` as a Windows Service | Use `pythonw.exe` + `subprocess` with CREATE_NO_WINDOW flag. Or document `nssm` wrapper |
| ANSI colors | Rich works on Windows Terminal but not old `cmd.exe` | Rich auto-detects. Document minimum terminal requirements |

**MAX_PATH handling** — use a path guard on all library operations:

```python
import sys
from pathlib import Path

MAX_PATH = 260 if sys.platform == "win32" else 4096

def validate_path_length(path: Path) -> Path:
    """Ensure path doesn't exceed OS limits. Windows needs \\?\ prefix."""
    resolved = path.resolve()
    if sys.platform == "win32" and len(str(resolved)) > MAX_PATH - 12:
        # -12 for file extension + null terminator safety margin
        resolved = Path("\\\\?\\") / resolved
    if len(str(resolved)) > 32767:  # absolute Windows limit
        raise OSError(f"Path too long: {resolved}")
    return resolved
```

**Windows daemon strategy:** Rather than implementing a full Windows Service (which requires `pywin32` and admin privileges), use Windows Task Scheduler:

```
rswd daemon start
  → Creates a scheduled task: "rswd-cli-daemon"
  → Triggers: At logon + every 24h
  → Action: pythonw -m rswd daemon --run-once
  → This is a one-shot check, not a persistent process

rswd daemon stop
  → Disables the scheduled task

rswd daemon status
  → Checks if the task exists and is enabled
```

### 11.2 macOS

| Concern | Mitigation |
|---------|------------|
| NFD Unicode paths | See Section 12 |
| User Agent identification | Include "macOS" in UA strings |
| Daemon | `launchctl` plist in `~/Library/LaunchAgents/` |
| Config path | `~/Library/Application Support/rswd/` (macOS convention) or `~/.config/rswd/` (XDG) |

**Platform detection for config path:**

```python
import platform
from pathlib import Path

def default_config_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "rswd"
    elif system == "Windows":
        return Path(os.environ.get("APPDATA", Path.home() / ".config")) / "rswd"
    else:  # Linux / BSD
        return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "rswd"
```

### 11.3 Linux

| Concern | Mitigation |
|---------|------------|
| Daemon | `systemd --user` unit in `~/.config/systemd/user/rswd.service` |
| XDG compliance | `$XDG_CONFIG_HOME/rswd/`, `$XDG_DATA_HOME/rswd/`, `$XDG_STATE_HOME/rswd/` |
| D-Bus keyring | `secretstorage` / `dbus` for keyring integration |

**systemd user unit:**

```
# ~/.config/systemd/user/rswd.service
[Unit]
Description=rswd-cli daemon
After=network-online.target

[Service]
Type=oneshot
ExecStart=%h/.local/bin/rswd daemon check
RemainAfterExit=no

[Install]
WantedBy=default.target
```

Plus a timer:

```
# ~/.config/systemd/user/rswd.timer
[Unit]
Description=Run rswd daily check

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

---

## 12. Unicode & Encoding Strategy

### 12.1 The NFC/NFD Problem

macOS's HFS+ and APFS filesystems normalize filenames to **NFD** (Canonical Decomposition) Unicode normalization. Linux uses **NFC** (Canonical Composition) by default. Streaming service APIs return **NFC** (é as a single codepoint U+00E9). macOS filesystem stores them as **NFD** (e + combining accent U+0065 U+0301).

This causes: `"Beyoncé" != "Beyoncé"` when the first is NFC and the second is NFD.

### 12.2 Solution

**Normalize all names at the DB boundary** — store as NFC internally, normalize to NFD on macOS filesystem writes:

```python
import unicodedata

def normalize_artist_name(name: str, filesystem: bool = False) -> str:
    """Normalize to NFC for DB / NFD for macOS filesystem."""
    nfc = unicodedata.normalize("NFC", name.strip())
    if filesystem and sys.platform == "darwin":
        return unicodedata.normalize("NFD", nfc)
    return nfc

def paths_match(db_path: str, fs_path: str) -> bool:
    """Compare two paths ignoring Unicode normalization differences."""
    return unicodedata.normalize("NFC", db_path) == unicodedata.normalize("NFC", fs_path)
```

### 12.3 DB Collation

SQLite's default `NOCASE` collation only handles ASCII. For proper Unicode case-insensitive matching, register a custom collation:

```python
import sqlite3
import unicodedata

def unicode_nocase_collation(a: str, b: str) -> int:
    """Unicode-aware case-insensitive collation for SQLite."""
    a = unicodedata.normalize("NFC", a).casefold()
    b = unicodedata.normalize("NFC", b).casefold()
    return (a > b) - (a < b)

conn = sqlite3.connect("library.db")
conn.create_collation("UNICODE_NOCASE", unicode_nocase_collation)
```

Apply to schema:

```sql
CREATE TABLE artists (
    ...
    UNIQUE(name COLLATE UNICODE_NOCASE)
);
```

### 12.4 Windows Filesystem Encoding

Windows uses UTF-16 internally. Python 3 handles this automatically when using `pathlib` and `open()`. The only concern is mojibake when a filename round-trips through a non-Unicode-aware tool. Not a concern for this project.

---

## 13. Library Scan Algorithm

### 13.1 Purpose

`rswd library scan --path ./music` imports existing audio files into the database. This is used for:
1. Initial import when switching from another manager
2. Discovering manually-added files
3. Verifying file integrity against the database

### 13.2 Algorithm

```
scan(directory)
  │
  ├─ recursive glob for *.flac *.mp3 *.m4a *.ogg *.opus *.wav
  │
  ├─ Phase 1: Header check (mutagen.File opens, reads duration/format)
  │   Skip files that fail mutagen.open() → mark as corrupted
  │
  ├─ Phase 2: Tag extraction
  │   For each valid file:
  │     title = tags.get("title")
  │     artist = tags.get("artist")
  │     album = tags.get("album")
  │     track_num = tags.get("tracknumber")
  │     mb_recording_id = tags.get(" MUSICBRAINZ_TRACKID")
  │     isrc = tags.get("isrc")
  │     bitrate, samplerate, bitdepth = audio.info.*
  │
  ├─ Phase 3: Matching
  │   Priority order:
  │     1. Match by file_path (fast: `SELECT * FROM tracks WHERE file_path = ?`)
  │        → Found: update mtime, check integrity
  │     2. Match by mb_recording_id
  │        → Found: adopt metadata, update file_path
  │     3. Match by isrc (if present)
  │        → Found: adopt metadata, update file_path
  │     4. Match by (artist + album + track_number + title)
  │        → Fuzzy match with normalized Unicode + casefold
  │        → Found: adopt metadata, update file_path
  │     5. No match → create new placeholder:
  │        INSERT INTO artists (name=artist, is_monitored=0)
  │        INSERT INTO albums (title=album, artist_id=..., download_status='external')
  │        INSERT INTO tracks (...)
  │
  ├─ Phase 4: AcoustID (optional, if configured)
  │   For files that failed all matching in Phase 3:
  │     Fingerprint via pyacoustid
  │     Lookup recording ID
  │     Retry MusicBrainz matching with recording ID
  │
  └─ Phase 5: Report
      Files matched: N
      Files imported: N
      Files corrupted: N
      Files unidentified: N
```

### 13.3 Edge Cases

| Case | Handling |
|------|----------|
| File moved since last scan | Detect by missing path, mark track as `missing`, don't delete. Re-match in next scan |
| Same file, different path (symlink/hardlink) | Compare inode on Linux/macOS, volume serial + file index on Windows |
| Corrupted header | mutagen raises `mutagen.MutagenError` → skip, log, increment corrupted counter |
| Tags in wrong encoding | mutagen handles CP1252/ISO-8859-1. If all else fails, field shows as replacement characters |
| Album split across directories | Match by `mb_albumid`. If no MBID, treat as separate albums. No heuristic merging |
| Multiple artists in single field | Respect delimiter (`,`, `;`, `feat.`) per `split_metadata` config flag. OrpheusDL-style |

---

## 14. Logging Architecture

### 14.1 Design

```
Library: standard library `logging`
Format: structured (key=value) for machine parsing + colored for human reading
Handlers:
  - Console: RichHandler (CLI commands, real-time feedback)
  - File: RotatingFileHandler (daemon mode, 10MB per file, 5 backups)
Level: INFO default, DEBUG for --verbose
```

### 14.2 Configuration

```python
import logging
import sys
from pathlib import Path
from rich.logging import RichHandler
from logging.handlers import RotatingFileHandler

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging(
    log_dir: Path,
    level: str = "INFO",
    verbose: bool = False,
    daemon_mode: bool = False,
):
    root = logging.getLogger("rswd")
    root.setLevel(logging.DEBUG if verbose else level)
    root.handlers.clear()

    # Console handler (Rich)
    if not daemon_mode:
        console = RichHandler(
            rich_tracebacks=True,
            markup=True,
            show_path=False,
        )
        console.setLevel(logging.DEBUG if verbose else logging.INFO)
        root.addHandler(console)

    # File handler (always, even in CLI mode)
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "rswd.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    file_handler.setLevel(logging.DEBUG)  # Always log everything to file
    root.addHandler(file_handler)

    # Third-party loggers
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("streamrip").setLevel(logging.WARNING)
    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
```

### 14.3 Log Line Examples

```
# CLI mode (console, RichHandler)
2026-07-09 12:00:00 [INFO] rswd.cli.artist: Added artist Radiohead (deezer)
2026-07-09 12:00:05 [INFO] rswd.backends.streamrip: Downloading album "OK Computer"
2026-07-09 12:01:30 [WARNING] rswd.metadata.lrclib: No lyrics found for track "Fitter Happier"
2026-07-09 12:01:31 [ERROR] rswd.backends.streamrip: Track 5 failed: QualityUnavailable (HiRes not available, fallback to CD)

# Daemon mode (file handler)
2026-07-09 03:00:00 [INFO] rswd.scheduler.jobs: check_new_releases: start
2026-07-09 03:00:01 [INFO] rswd.scheduler.jobs: Checking 12 monitored artists
2026-07-09 03:00:45 [INFO] rswd.scheduler.jobs: Found 1 new album: "Moon Shaped Pool" by Radiohead
2026-07-09 03:00:46 [INFO] rswd.backends.streamrip: Downloading "Moon Shaped Pool"
2026-07-09 03:12:30 [INFO] rswd.scheduler.jobs: check_new_releases: complete (11 tracks downloaded)
```

### 14.4 Logger Hierarchy

```
rswd
├── rswd.cli
│   ├── rswd.cli.artist
│   ├── rswd.cli.album
│   ├── rswd.cli.library
│   └── rswd.cli.daemon
├── rswd.db
│   └── rswd.db.repository
├── rswd.backends
│   ├── rswd.backends.base
│   ├── rswd.backends.streamrip_
│   └── rswd.backends.orpheus
├── rswd.metadata
│   ├── rswd.metadata.lrclib
│   ├── rswd.metadata.musicbrainz
│   ├── rswd.metadata.replaygain
│   └── rswd.metadata.acoustid
├── rswd.scheduler
│   └── rswd.scheduler.jobs
└── rswd.config
```

Each module gets its own logger via `logger = logging.getLogger(__name__)`.

---

## 15. Configuration Precedence

### 15.1 Resolution Order (highest to lowest)

```
1. CLI flags
2. Environment variables (rswd_*)
3. Config file (~/.config/rswd/config.toml)
4. Built-in defaults
```

### 15.2 Environment Variable Mapping

| Environment Variable | Overrides Config Key | Example |
|---------------------|---------------------|---------|
| `rswd_CONFIG` | Config file path | `rswd_CONFIG=/etc/rswd/config.toml` |
| `rswd_DOWNLOAD_PATH` | `core.download_path` | `rswd_DOWNLOAD_PATH=/mnt/music` |
| `rswd_QUALITY` | `quality.default` | `rswd_QUALITY=3` |
| `rswd_CODEC` | `quality.codec` | `rswd_CODEC=ALAC` |
| `rswd_LOG_LEVEL` | `core.log_level` | `rswd_LOG_LEVEL=DEBUG` |
| `rswd_DEEZER_ARL` | `services.deezer.arl` | `rswd_DEEZER_ARL=xxxxx` |
| `rswd_TIDAL_ACCESS_TOKEN` | `services.tidal.access_token` | `rswd_TIDAL_ACCESS_TOKEN=xxxxx` |
| `rswd_CONCURRENCY` | `quality.concurrency` | `rswd_CONCURRENCY=5` |
| `rswd_DAEMON_INTERVAL` | `daemon.check_interval_hours` | `rswd_DAEMON_INTERVAL=12` |

### 15.3 Implementation

```python
import os
from dataclasses import dataclass, field

ENV_PREFIX = "rswd_"
ENV_MAP = {
    "download_path": "rswd_DOWNLOAD_PATH",
    "quality_default": "rswd_QUALITY",
    "quality_codec": "rswd_CODEC",
    "log_level": "rswd_LOG_LEVEL",
    "deezer_arl": "rswd_DEEZER_ARL",
    "tidal_access_token": "rswd_TIDAL_ACCESS_TOKEN",
    "concurrency": "rswd_CONCURRENCY",
    "daemon_interval": "rswd_DAEMON_INTERVAL",
}

def apply_env_overrides(config: ConfigData) -> ConfigData:
    """Overlay environment variables onto config."""
    for attr, env_key in ENV_MAP.items():
        val = os.environ.get(env_key)
        if val is not None:
            _set_deep_attr(config, attr, _coerce(val))
    return config

def _coerce(val: str):
    """Convert string env var to appropriate type."""
    if val.lower() in ("true", "false"):
        return val.lower() == "true"
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val
```

---

## 16. Daemon Management

### 16.1 Cross-Platform Strategy

The daemon is **not a persistent background process**. It's a **trigger-based job runner**:

```
rswd daemon start
  → Installs a platform-specific trigger that runs:
      rswd daemon check
    on a schedule (default: 24h)

rswd daemon check
  → Loads config
  → Connects to DB
  → Runs check_new_releases()
  → Exits (typically <5 minutes)
  → Exit code 0 = success, non-zero = failure
```

Rationale: A persistent process wastes memory for something that runs once daily and completes in seconds. Platform schedulers (systemd timers, launchctl, Windows Task Scheduler) are battle-tested and survive reboots.

### 16.2 Platform Implementation

| Platform | Mechanism | Trigger | Persistence | User-Facing Command |
|----------|-----------|---------|-------------|-------------------|
| Linux | `systemd --user` timer | `OnCalendar=daily` + `Persistent=true` | Survives reboot | `rswd daemon start` = `systemctl --user enable rswd.timer` |
| macOS | `launchctl` plist | `StartCalendarInterval` Hour:Minute | Survives reboot | `rswd daemon start` = `launchctl load ~/Library/LaunchAgents/rswd.plist` |
| Windows | Task Scheduler | `Daily` trigger at user's login | Survives reboot | `rswd daemon start` = `schtasks /create /tn rswd /tr "python -m rswd daemon check" /daily /st 03:00` |

### 16.3 Daemon Commands

```
rswd daemon install     # Create scheduler entry (alias for 'start')
rswd daemon uninstall   # Remove scheduler entry (alias for 'stop')
rswd daemon start       # Enable scheduled checks
rswd daemon stop        # Disable scheduled checks
rswd daemon status      # Is the scheduler entry installed + enabled?
rswd daemon check       # Run the check immediately (blocking)
rswd daemon log         # Tail the most recent daemon run log
```

### 16.4 Daemon Locking

Prevent concurrent `check` runs:

```python
import fcntl  # Linux/macOS
import msvcrt  # Windows

class DaemonLock:
    """Prevent multiple check_new_releases from running simultaneously."""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path

    def __enter__(self):
        if sys.platform == "win32":
            self.fd = open(self.lock_path, "w")
            try:
                msvcrt.locking(self.fd.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self.fd.close()
                raise DaemonLockError("Another daemon instance is running")
        else:
            self.fd = open(self.lock_path, "w")
            try:
                fcntl.flock(self.fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError:
                self.fd.close()
                raise DaemonLockError("Another daemon instance is running")
        return self

    def __exit__(self, *args):
        if sys.platform == "win32":
            msvcrt.locking(self.fd.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(self.fd.fileno(), fcntl.LOCK_UN)
        self.fd.close()
        self.lock_path.unlink(missing_ok=True)
```

---

## 17. Database Migration Strategy

### 17.1 Design

**No ORM migration framework** (no Alembic, no Django migrations). SQLite schema versioning with sequential integer versions and explicit DDL scripts.

### 17.2 Version Table

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    checksum TEXT               -- SHA256 of the migration SQL
);
```

### 17.3 Migration Scripts

```
src/rswd/db/
├── schema.py           # Current DDL + migration orchestrator
└── migrations/
    ├── __init__.py
    ├── v001_initial.sql     # 001: Create all initial tables
    ├── v002_quality.sql     # 002: Add quality columns to albums
    └── v003_indexes.sql     # 003: Add missing indexes
```

### 17.4 Migration Orchestrator

```python
import hashlib
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

def ensure_schema(db_path: str):
    """Create or migrate a database to the latest version."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Determine current version
    try:
        current = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_version"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        current = 0

    # Apply pending migrations in order
    for migration in sorted(MIGRATIONS_DIR.glob("v*.sql")):
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
        logger.info(f"Applied DB migration {migration.stem}")

    conn.close()
```

### 17.5 Migration Rules

1. **Never modify an existing migration.** If it's committed, it's immutable.
2. **Never delete columns.** Add new columns but don't remove old ones (backward compat).
3. **Use `ALTER TABLE ADD COLUMN`** for additive changes.
4. **Complex migrations** (data transforms) use a temp table: `CREATE temp_... AS SELECT ...; DROP ...; CREATE ...; INSERT INTO ... SELECT ...; DROP temp_...`
5. **Test each migration** against a copy of the current production schema before deploying.

---

## 18. Service Rate Limits

### 18.1 Streaming Services

| Service | Endpoint | Limit | Penalty | Mitigation |
|---------|----------|-------|---------|------------|
| Deezer | `api.deezer.com` | 50 req/5s | 403 + temporary ban | `asyncio.sleep(0.1)` between requests |
| Deezer | `www.deezer.com` (GW API) | 50 req/5s | 403 | Same. Used by streamrip internally |
| Tidal | `api.tidal.com` | Not documented | 429 + temporary ban | Exponential backoff on 429. Max 5 req/s empirically |
| Qobuz | `www.qobuz.com/api.json` | ~1 req/s (not documented) | 429 | 1 req/s enforced by streamrip client |
| SoundCloud | `api.soundcloud.com` | Not documented | 429 | 1 req/s conservative |
| LRCLIB | `lrclib.net/api` | Configurable per IP | 429 | Use `requests_per_minute` header. Start at 60/min |
| MusicBrainz | `musicbrainz.org/ws/2` | 1 req/s | 503 | `musicbrainzngs.set_rate_limit(1.0)` enforces this |
| AcoustID | `api.acoustid.org/v2` | 3 req/s | 503 | `pyacoustid` enforces this internally |

### 18.2 Implementation

```python
import asyncio
import time
from collections import defaultdict

class RateLimiter:
    """Token-bucket rate limiter per endpoint."""

    def __init__(self, default_rate: float = 1.0):
        self.rates: dict[str, float] = defaultdict(lambda: default_rate)
        self._last_call: dict[str, float] = defaultdict(float)

    def set_rate(self, endpoint: str, requests_per_second: float):
        self.rates[endpoint] = requests_per_second

    async def acquire(self, endpoint: str):
        """Wait if necessary to respect the rate limit."""
        rate = self.rates[endpoint]
        if rate <= 0:
            return
        elapsed = time.monotonic() - self._last_call[endpoint]
        min_interval = 1.0 / rate
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self._last_call[endpoint] = time.monotonic()

rate_limiter = RateLimiter()
rate_limiter.set_rate("deezer", 10.0)  # 50 req/5s = 10 req/s
rate_limiter.set_rate("tidal", 5.0)
rate_limiter.set_rate("qobuz", 1.0)
rate_limiter.set_rate("soundcloud", 1.0)
rate_limiter.set_rate("lrclib", 1.0)
rate_limiter.set_rate("musicbrainz", 1.0)
```

### 18.3 429 Handling

```python
import httpx

async def request_with_retry(
    client: httpx.AsyncClient,
    endpoint: str,
    url: str,
    max_retries: int = 3,
) -> httpx.Response:
    """Make a request with rate limiting and 429 retry logic."""
    for attempt in range(max_retries):
        await rate_limiter.acquire(endpoint)
        resp = await client.get(url)
        if resp.status_code != 429:
            return resp
        retry_after = int(resp.headers.get("Retry-After", 5))
        logger.warning(f"429 on {endpoint}, retrying in {retry_after}s (attempt {attempt+1})")
        await asyncio.sleep(retry_after)
    raise RateLimitError(f"Exceeded max retries for {url}")
```

---

## 19. Migration Paths

### 19.1 Importing from rswd

rswd stores its data in a SQLite database at `~/.config/rswd/rswd.db`. The `rswd import-from-rswd` command:

```python
# src/rswd/cli/import_.py
@cli.command("import-from-rswd")
@click.option("--source", default="rswd", type=click.Choice(["rswd", "beets"]))
@click.option("--db-path", default=None, help="Path to source database")
def import_from(source, db_path):
    """Import artist subscriptions from another music manager."""
    if source == "rswd":
        _import_rswd(db_path)
    elif source == "beets":
        _import_beets(db_path)
```

**rswd schema mapping:**

| rswd Table | rswd-cli Table | Notes |
|-------------|------------------|-------|
| `Artists` | `artists` | Map `ForeignArtistId` → `mb_artistid`, `ArtistName` → `name`, `Monitored` → `is_monitored` |
| `Albums` | `albums` | Map `ForeignAlbumId` → `mb_albumid`, `Title` → `title`, `ReleaseDate` → `year` |
| `Tracks` | `tracks` | Map track metadata |
| `ArtistMetadata` | `artists.metadata_blob` | Store MB data as JSON |
| `QualityProfiles` | `artists.monitor_quality` | Map: rswd quality profile ID to our quality tier (0-3) |

**rswd download history is NOT imported.** The user will re-download via streaming services.

### 19.2 Importing from beets

Beets stores its data in `~/.config/beets/library.db`. The mapping:

```
beets.items → tracks
  item.artist → tracks.artist
  item.album → albums.title
  item.title → tracks.title
  item.mb_trackid → tracks.mb_recording_id
  item.path → tracks.file_path (keep existing files)
  item.added → tracks.added_at

beets.albums → albums
  album.mb_albumid → albums.mb_albumid
  album.albumartist → albums.albumartist (denormalized)

Note: beets has no artist table (denormalized). We extract distinct artist names
and create artist entries with is_monitored=0.
```

### 19.3 Importing Existing Files (No DB)

`rswd library scan --path ./music` (see Section 13). This is the primary import mechanism for users with no existing music manager.

---

## 20. Implementation Roadmap

### Phase 1 — Core Skeleton (0.1.0)
- [ ] Project scaffolding: `pyproject.toml`, `src/rswd/` package structure
- [ ] Config loading (`config.py`): TOML parsing, validation, defaults
- [ ] Database schema + migration (`db/schema.py`, `db/repository.py`)
- [ ] CLI skeleton with `--help` (`cli/app.py`)

### Phase 2 — Backend Integration (0.2.0)
- [ ] Backend abstraction (`backends/base.py`)
- [ ] StreamripBackend: search, get_album_info, download_album
- [ ] Service credential validation
- [ ] Basic download flow: search → download → post-process (move, rename, register)
- [ ] CLI commands: `artist add`, `album search`, `album download`

### Phase 3 — Library Management (0.3.0)
- [ ] `artist list`, `artist remove`
- [ ] `album list`, `library status`
- [ ] `library scan` (import existing files into DB)
- [ ] Quality tracking and upgrade detection
- [ ] LRCLIB lyrics enrichment (`metadata/enrichment.py`)
- [ ] LRCLIB integration tests

### Phase 4 — Monitoring & Daemon (0.4.0)
- [ ] `artist monitor/unmonitor`
- [ ] APScheduler integration (`scheduler/`)
- [ ] `check_new_releases` job
- [ ] `daemon start/stop/status`
- [ ] MusicBrainz MBID enrichment (`metadata/musicbrainz.py`)
- [ ] Cover art fallback chain (`metadata/covers.py`)

### Phase 5 — Advanced Metadata (0.5.0)
- [ ] ReplayGain 2.0 tags (`metadata/replaygain.py`) — uses ffmpeg ebur128 + mutagen
- [ ] AcoustID fingerprinting for `library scan` (`metadata/acoustid.py`)

### Phase 6 — Polish (0.6.0+)
- [ ] OrpheusDL backend (Apple Music, Spotify, YouTube)
- [ ] Enhanced LRC / karaoke word-level lyrics support
- [ ] Rich progress bars for downloads
- [ ] Config file generation (`rswd init`)
- [ ] Logging to file with rotation
- [ ] Comprehensive test suite

---

## 10. Appendix

### A. Config Reference

```toml
# config.toml — Full reference with all options
[core]
download_path = "~/music"
library_db = "~/.local/share/rswd/library.db"
jobs_db = "~/.local/share/rswd/jobs.db"
log_level = "INFO"           # DEBUG, INFO, WARNING, ERROR

[daemon]
enabled = false
check_interval_hours = 24
check_at_startup = true

[quality]
default = 2                  # 0=128k, 1=320k, 2=CD, 3=HiRes
codec = ""                   # empty = keep original, or: FLAC, ALAC, MP3, AAC
concurrency = 3

[filepaths]
album_folder = "{albumartist}/{album} ({year})"
track_file = "{tracknum:02d}. {artist} - {title}{ext}"

[metadata]
embed_cover = true
cover_size = 1400
min_cover_bytes = 30000
cover_fallback = true

[metadata.lyrics]
embed = true
prefer_synced = true
providers = ["lrclib"]

[metadata.musicbrainz]
enrichment = false
rate_limit = 1.0

[metadata.replaygain]
enabled = false
mode = "album"

[metadata.acoustid]
enabled = false
api_key = ""

[backend]
name = "streamrip"

[backend.streamrip]
config_path = ""

[backend.orpheusdl]
install_path = ""

[services.deezer]
arl = ""

[services.tidal]
access_token = ""
refresh_token = ""
user_id = ""
country_code = ""
token_expiry = ""

[services.qobuz]
email_or_userid = ""
password_or_token = ""
app_id = ""
secrets = []

[services.soundcloud]
client_id = ""
app_version = ""
```

### B. Streamrip Config Mapping

| Our Config Key | streamrip Config Key | Type | Notes |
|---------------|---------------------|------|-------|
| `quality.default` | `session.{svc}.quality` | int 0-4 | Mapped per service; Tidal max=3 |
| `quality.codec` | `session.conversion.codec` | str | Empty → disabled |
| `download_path` | `session.downloads.folder` | str | Overridden per download |
| `quality.concurrency` | `session.downloads.concurrency` | int | |
| `services.deezer.arl` | `session.deezer.arl` | str | |
| `services.tidal.*` | `session.tidal.*` | various | All 4 fields mapped |
| `services.qobuz.*` | `session.qobuz.*` | various | email/password or token |
| `services.soundcloud.*` | `session.soundcloud.*` | various | client_id + app_version |

### C. SQLite Schema Diagram (ASCII)

```
┌──────────────────────┐       ┌───────────────────────────┐
│     schema_version   │       │      scheduler_log         │
├──────────────────────┤       ├───────────────────────────┤
│ PK version           │       │ PK id                     │
│    applied_at        │       │    job_name               │
└──────────────────────┘       │    started_at             │
                               │    completed_at            │
┌──────────────────────┐       │    status                 │
│       artists        │       │    message                │
├──────────────────────┤       │    albums_found           │
│ PK id                │       │    tracks_added           │
│    name              │       │    tracks_dled            │
│    sort_name         │       └───────────────────────────┘
│    mb_artistid  (UQ) │
│    is_monitored      │       ┌───────────────────────┐
│    monitor_quality   │       │     download_log       │
│    added_at          │       ├───────────────────────┤
│    metadata_blob     │       │ PK id                 │
└──────────┬───────────┘       │    track_id       (FK)│
           │ 1                  │    service            │
           │                    │    quality             │
           ▼ *                 │    file_path           │
┌──────────────────────┐       │    file_size           │
│       albums         │       │    checksum            │
├──────────────────────┤       │    downloaded_at       │
│ PK id                │       └───────────────────────┘
│    artist_id    (FK) │
│    title             │
│    year              │
│    album_type        │
│    mb_albumid        │
│    mb_release_groupid│
│    total_tracks      │
│    download_status   │
│    quality_tier      │
│    service           │
│    service_id        │
│    added_at          │
│    metadata_blob     │
└──────────┬───────────┘
           │ 1
           │
           ▼ *
┌──────────────────────┐
│       tracks         │
├──────────────────────┤
│ PK id                │
│    album_id    (FK)  │
│    title             │
│    track_number      │
│    disc_number       │
│    duration          │
│    artist            │
│    file_path   (UQ)  │
│    file_format       │
│    bitrate           │
│    sample_rate       │
│    bit_depth         │
│    isrc              │
│    mb_recording_id   │
│    service_id        │
│    download_status   │
│    added_at          │
└──────────────────────┘
```
