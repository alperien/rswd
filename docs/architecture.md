# rswd — Technical Architecture

## Overview

rswd is a CLI-based automated music library manager. It searches streaming services
(primarily Deezer), downloads albums via streamrip, organizes files by
artist/album, enriches metadata (lyrics, ReplayGain, MusicBrainz IDs, AcoustID),
and runs a headless daemon for periodic new-release checks.

Single CLI interface (`python -m rswd`): click-based subcommands (artist, album,
library, daemon, shell).

Python 3.11+ required. 187 tests.

---

## Directory Layout

```
src/rswd/
  __init__.py          # version = "0.1.0"
  __main__.py          # entry point → cli()
  config.py            # ConfigData dataclasses, TOML/env/keyring loading
  search.py            # Searcher: Deezer API (httpx)
  download.py          # DownloadPipeline: verify, checksum, move, register
  library.py           # LibraryScanner: scan directory, import tags, prune
  log.py               # RichHandler console + RotatingFileHandler
  util.py              # sanitize_filename, normalize_name, validate_path_length
  backends/
    base.py            # Abstract base: SearchResult, AlbumInfo, TrackInfo, DownloadResult
    streamrip_.py      # StreamripBackend: search, get_album_info, download via streamrip
    orpheus.py         # OrpheusBackend: stub (not implemented)
  cli/
    app.py             # click group, load_config, ensure_schema
    artist.py          # artist add/list/remove/monitor/unmonitor
    album.py           # album list/search/download/fetch
    library.py         # library status/scan/prune/import
    daemon.py          # daemon start/stop/status/check (APScheduler)
    shell.py           # interactive REPL: search → pick → download
  db/
    schema.py          # ensure_schema: migration runner (WAL, foreign_keys)
    models.py          # Artist, Album, Track, DownloadLogEntry, SchedulerLogEntry
    repository.py      # Repository: full CRUD, UNICODE_NOCASE collation
    migrations/
      v001_initial.sql # 6 tables: artists, albums, tracks, download_log, scheduler_log
  scheduler/
    __init__.py        # APScheduler lifecycle, DaemonState

  metadata/
    lrclib.py          # LRCLibProvider: fetch lyrics from lrclib.net
    lyrics.py          # LyricsEnricher: fetch & embed in FLAC/MP3 tags
    musicbrainz_.py    # MusicBrainzEnricher: search + write MBIDs
    replaygain.py      # ReplayGainScanner: ffmpeg EBU R128 + mutagen write
    acoustid_.py       # AcoustIDMatcher: fingerprint + lookup via pyacoustid
```

---

## Data Flow

### Search → Download → Library (CLI `rswd album fetch`)

```
1. Searcher.search_album("query")
   → GET https://api.deezer.com/search/album?q=query
   → list[SearchHit] (service, service_id, title, artist, year, track_count)

2. Repository.add_artist(name) → artist_id
   Repository.add_album(artist_id=..., title=..., year=..., service_id=...) → album_id

3. StreamripBackend.get_album_info("deezer", "266475492")
   → GET https://api.deezer.com/album/266475492
   → AlbumInfo (title, artist, year, tracks=[TrackInfo...])

4. Repository.add_track(album_id=..., ...) → track_id  (per track)

5. StreamripBackend.download_album(service, service_id, info, output_dir)
   → Builds streamrip Config (BLANK_CONFIG_PATH + overrides)
   → asyncio.run:
       async with Main(config) as m:
         await m.add_by_id(service, "album", service_id)
         await m.resolve()
         await m.rip()
   → _scan_output: matches files by service_id or track_number
   → list[DownloadResult] (track_info, file_path, success)

6. DownloadPipeline.process_track(source, album_id, track_id, ...)
   → verify_file: mutagen opens & checks
   → compute_checksum: SHA-256
   → move_to_library:
       dest = <download_path>/<album_artist>/<album> (<year>)/<NN>. <artist> - <title>.<ext>
   → Repository.update_track_file(track_id, file_path, format, bitrate, sr, depth)
   → Repository.add_download_log(track_id, service, quality, file_path, size, checksum)

7. Repository.update_album_status(album_id, "downloaded" | "partial")
```

### Daemon Monitoring

```
rswd daemon start --foreground
  → BackgroundScheduler, interval = config.daemon.check_interval_hours
  → Job: _check_monitored_artists(repo)
      For each monitored artist:
        Searcher.search_album(artist.name) → hits
        For each hit:
          repo.album_exists(artist.id, title, year) → if not → repo.add_album(...)
```

---

## Configuration Subsystem (`rswd/config.py`)

### Class Hierarchy

```
ConfigData
├── core: CoreConfig           (download_path, library_db, jobs_db, log_level)
├── daemon: DaemonConfig       (enabled, check_interval_hours, check_at_startup)
├── quality: QualityConfig      (default=2, codec="", concurrency=3)
├── filepaths: FilepathsConfig (album_folder, track_file)
├── metadata: MetadataConfig
│   ├── lyrics: LyricsConfig       (embed=True, prefer_synced=True, providers)
│   ├── musicbrainz: MusicBrainzConfig (enrichment=False, rate_limit=1.0)
│   ├── replaygain: ReplayGainConfig   (enabled=False, mode="album")
│   └── acoustid: AcoustIDConfig       (enabled=False, api_key="")
├── backend: BackendConfig
│   ├── streamrip: StreamripBackendConfig (config_path)
│   └── orpheusdl: OrpheusDLConfig  (install_path)
└── services: ServicesConfig
    ├── deezer: ServiceCredentials
    ├── tidal: ServiceCredentials
    ├── qobuz: ServiceCredentials
    └── soundcloud: ServiceCredentials
```

### Loading Order

```
load_config(config_path=None)
  1. Read config.toml (TOML) from default_config_dir()/config.toml
  2. _dict_to_dataclass(ConfigData, raw_dict)
  3. _apply_env_overrides(config)  — see ENV_MAP below
  4. Expand ~ in paths
  5. try_keyring_load(config)  — keyring.get_password per service+field
  6. Return ConfigData
```

### Environment Variable Overrides

| ENV | Config Attribute |
|-----|-----------------|
| `RSWD_DOWNLOAD_PATH` | `core.download_path` |
| `RSWD_QUALITY` | `quality.default` |
| `RSWD_CODEC` | `quality.codec` |
| `RSWD_LOG_LEVEL` | `core.log_level` |
| `RSWD_DEEZER_ARL` | `services.deezer.arl` |
| `RSWD_TIDAL_ACCESS_TOKEN` | `services.tidal.access_token` |
| `RSWD_CONCURRENCY` | `quality.concurrency` |
| `RSWD_DAEMON_INTERVAL` | `daemon.check_interval_hours` |

### Config Paths (Platform-Aware)

- Config dir: `$APPDATA/rswd` (Win), `~/.config/rswd` (Linux), `~/Library/Application Support/rswd` (macOS)
- Data dir: `$LOCALAPPDATA/rswd` (Win), `~/.local/share/rswd` (Linux), same as config (macOS)
- Default download: `~/music`

### Sensitive Data Redaction

`redact_sensitive()` replaces ARL, tokens, passwords with `<redacted>` for safe log output.
Patterns defined in `SENSITIVE_PATTERNS` list.

---

## Database Subsystem (`rswd/db/`)

### Schema (v001_initial.sql)

6 tables with WAL journal mode and foreign keys enabled.

#### `artists`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | autoincrement |
| name | TEXT NOT NULL | |
| sort_name | TEXT | |
| mb_artistid | TEXT UNIQUE | MusicBrainz ID |
| is_monitored | INTEGER | 0/1 |
| monitor_quality | INTEGER | default 2 |
| added_at | TEXT | ISO 8601 |
| metadata_blob | TEXT | JSON |

Indices: name (NOCASE), monitored, mbid.

#### `albums`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| artist_id | INTEGER FK → artists | ON DELETE CASCADE |
| title | TEXT NOT NULL | |
| year | INTEGER | |
| album_type | TEXT | e.g. "album", "single" |
| mb_albumid, mb_release_groupid | TEXT | MusicBrainz |
| total_tracks | INTEGER | |
| download_status | TEXT | "none", "partial", "downloaded" |
| quality_tier | INTEGER | |
| service, service_id | TEXT | e.g. "deezer", "266475492" |
| added_at | TEXT | |
| metadata_blob | TEXT | |
| UNIQUE(artist_id, title) | | |

Indices: artist_id, title (NOCASE), status, mbid.

#### `tracks`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| album_id | INTEGER FK → albums | CASCADE |
| title | TEXT NOT NULL | |
| track_number, disc_number | INTEGER | |
| duration | REAL | seconds |
| artist | TEXT | track artist (may differ from album artist) |
| file_path | TEXT | |
| file_format | TEXT | "FLAC", "MP3" |
| bitrate, sample_rate, bit_depth | INTEGER | |
| isrc, mb_recording_id, service_id | TEXT | |
| download_status | TEXT | "pending", "downloaded", "missing" |
| added_at | TEXT | |

Indices: album_id, status, unique partial index on file_path WHERE NOT NULL.

#### `download_log`
| Column | Type |
|--------|------|
| id | INTEGER PK |
| track_id | INTEGER FK → tracks |
| service | TEXT |
| quality | INTEGER |
| file_path | TEXT |
| file_size | INTEGER |
| checksum | TEXT (SHA-256) |
| downloaded_at | TEXT |

#### `scheduler_log`
| Column | Type |
|--------|------|
| id | INTEGER PK |
| job_name | TEXT |
| started_at, completed_at | TEXT |
| status | TEXT |
| message | TEXT |
| albums_found, tracks_added, tracks_dled | INTEGER |

#### `schema_version`
| Column | Type |
|--------|------|
| version | INTEGER PK |
| applied_at | TEXT |
| checksum | TEXT (SHA-256 of migration SQL) |

### Repository Pattern

`Repository(db_path)` manages a single `sqlite3.Connection` with lazy connect.

- **Custom collation**: `UNICODE_NOCASE` — NFC-normalizes and casefolds for
  case-insensitive artist/album name lookups that handle Unicode correctly.
- **Context manager**: `with repo:` calls `connect()`/`close()`.
- **Foreign keys**: enforced by `PRAGMA foreign_keys=ON`.
- **WAL mode**: `PRAGMA journal_mode=WAL` for concurrent reads.
- **Row factory**: `sqlite3.Row` for dict-like access.

Methods: `add_artist`, `get_artist`, `get_artist_by_name`, `list_artists`,
`remove_artist`, `set_monitored`, `add_album`, `album_exists`, `get_album`,
`list_albums`, `update_album_status`, `add_track`, `update_track_file`,
`list_tracks`, `get_track_by_path`, `add_download_log`, `library_stats`.

### Migration System

`ensure_schema(db_path)`:
1. Reads current version from `schema_version` table (0 if table missing)
2. Sorts `migrations/v*.sql` files by version number
3. Executes each unapplied migration, records SHA-256 checksum

---

## Backend Subsystem (`rswd/backends/`)

### Base Classes (`base.py`)

```python
@dataclass(frozen=True)
class SearchResult:     service, media_type, service_id, title, artists, year, ...
@dataclass(frozen=True)
class TrackInfo:        service, service_id, title, artist, album, track_number, ...
@dataclass(frozen=True)
class AlbumInfo:        service, service_id, title, artist, year, tracks=[], ...
@dataclass
class DownloadResult:   track_info, file_path, success, error

class SearchDownloadBackend(ABC):
    search(media_type, query, limit) → list[SearchResult]
    search_artist_discography(artist_name) → dict[str, list[AlbumInfo]]
    get_album_info(service, service_id) → AlbumInfo
    download_album(service, service_id, album_info, output_dir, quality, codec) → list[DownloadResult]
    login_and_validate() → dict[str, bool]
```

### StreamripBackend (`streamrip_.py`)

Primary backend. Supports Deezer/Tidal/Qobuz/Soundcloud via streamrip.

**Search**: Delegates to `Searcher` (httpx → api.deezer.com).

**get_album_info**: For Deezer, fetches `https://api.deezer.com/album/{id}` directly
with httpx and builds `AlbumInfo` with per-track `TrackInfo`. Falls through to
`NotImplementedError` for other services.

**download_album**: Builds a streamrip `Config` from `BLANK_CONFIG_PATH`,
overrides session fields (ARL, tokens, download folder, codec, concurrency),
creates `Main`, calls `add_by_id` → `resolve` → `rip` in an asyncio event loop,
then scans output directory for downloaded files.

**streamrip v2.1.0 compatibility notes**:
- `Config.__init__` requires `path` argument — uses `BLANK_CONFIG_PATH`
- Database config must be disabled (empty paths cause AssertionError)
- `session.downloads.concurrency` is bool, `max_connections` is int
- Missing ARL triggers interactive prompt (Rich) → EOFError in non-TTY contexts

### OrpheusBackend (`orpheus.py`)

Stub only — all methods either return empty lists or raise NotImplementedError.
Entry point registered in `pyproject.toml` under `rswd.backends`.

---

## Search Subsystem (`rswd/search.py`)

`Searcher` wraps `httpx.Client(timeout=15)` and hits the public Deezer API.

| Method | API Endpoint | Returns |
|--------|-------------|---------|
| `search_album(query)` | `GET /search/album?q=` | `list[SearchHit]` (max 15) |
| `search_artist(query)` | `GET /search/artist?q=` | `list[SearchHit]` (max 10) |
| `get_artist_discography(name)` | `GET /artist/{id}/albums` | `list[dict]` (max 100) |

Tidal search falls back to Deezer. Unknown services fall back to Deezer.

`SearchHit` is a frozen dataclass: service, service_id, title, artist, album,
year, track_count, cover_url, hit_type.

---

## Download Pipeline (`rswd/download.py`)

### `DownloadPipeline`

| Method | Purpose |
|--------|---------|
| `verify_file(path)` | Opens with mutagen, checks non-zero size |
| `compute_checksum(path)` | SHA-256 (64KB blocks) |
| `move_to_library(...)` | Formats path from config patterns, shutil.move |
| `process_track(...)` | Full pipeline: verify → checksum → move → update DB → log |

### File Organization

Album folder pattern: `{albumartist}/{album} ({year})`
Track file pattern:     `{tracknum:02d}. {artist} - {title}{ext}`

Both patterns defined in `FilepathsConfig` and are configurable. Values are
sanitized via `util.sanitize_filename()` which strips illegal chars (`<>:"/\|?*`),
trailing dots/spaces, handles Windows reserved names (CON, PRN, etc.), and
truncates to 200 chars.

Path length protection: Uses `\\?\` prefix on Windows if path > 248 chars.
Hard cap at 32767 chars.

---

## Library Scanner (`rswd/library.py`)

`LibraryScanner` walks a directory tree and imports audio files into the database.

### scan_directory(path) → stats dict

For each file with audio extension (`.flac`, `.mp3`, `.m4a`, `.ogg`, `.opus`,
`.wav`, `.aiff`, `.wma`):
1. Check if already in DB by file_path → "matched"
2. Read tags with mutagen → extract title, artist, album, tracknumber, albumartist,
   date, discnumber, tracktotal
3. Find or create `Artist` (by albumartist)
4. Find or create `Album` (by artist_id + title, case-insensitive)
5. Add `Track` with audio technical info (bitrate, sample_rate, bit_depth)
6. Register file path in DB

### prune_missing() → count

Sets `file_path=NULL, download_status='missing'` for DB tracks whose files no
longer exist on disk.

### Tag parsing helpers

`_tag_value(tags, key)`: tries `key`, `KEY`, `Key` forms. Handles list values.
`_tag_int(tags, key)`: parses `"5/12"` → 5.
`_get_duration(audio)`: `audio.info.length`.

---

## Metadata Subsystem (`rswd/metadata/`)

### LRCLib Provider (`lrclib.py`)

`LRCLibProvider.fetch(track, artist, album, duration)`:
- `GET https://lrclib.net/api/get?track_name=...&artist_name=...`
- Returns `LyricsResult(source, plain, synced, is_instrumental)`
- 404 → None. HTTP errors → logged, None.

### Lyrics Enricher (`lyrics.py`)

`LyricsEnricher.fetch_and_embed(file_path, track, artist, album)`:
1. Fetch from LRCLib
2. Embed via mutagen:
   - ID3 (MP3): `USLT` frame
   - Vorbis/APEv2 (FLAC/etc): `LYRICS` tag
3. Respects `prefer_synced` config — synced lyrics preferred when available

### MusicBrainz Enricher (`musicbrainz_.py`)

Optional dependency (`musicbrainzngs`). Gracefully degrades if not installed.

| Method | Purpose |
|--------|---------|
| `enrich_artist(name)` | Search → return first result dict |
| `enrich_album(title, artist)` | Search releases → return first result |
| `enrich_track(recording, artist)` | Search recordings → return first result |
| `enrich_artist_in_db(repo, artist_id)` | Search + write `mb_artistid`, `sort_name` |
| `enrich_album_in_db(repo, album_id)` | Search + write `mb_albumid`, `mb_release_groupid` |

Rate-limited to 1 request/second by default (MusicBrainz policy).

### ReplayGain Scanner (`replaygain.py`)

`ReplayGainScanner` uses ffmpeg with `ebur128` filter:

```
ffmpeg -i <file> -af ebur128 -f null -
```

Parses `I:  -8.3 dB` → track gain, `Peak:  -0.5 dBFS` → track peak.
Writes via mutagen: `REPLAYGAIN_TRACK_GAIN` / `REPLAYGAIN_TRACK_PEAK` tags
(ID3: TXXX frames).

### AcoustID Matcher (`acoustid_.py`)

Optional dependency (`pyacoustid` + `chromaprint`). Gracefully degrades.

- `fingerprint(file)`: `acoustid.fingerprint_file()` → duration + fingerprint
- `lookup(file)`: fingerprint → `acoustid.lookup()` → filter >0.5 score →
  return `mb_recording_id`, title, artist

---

## CLI Subsystem (`rswd/cli/`)

### App Entry Point (`app.py`)

```python
@click.group()
@click.option("--config", "-c", ...)
@click.option("--verbose", "-v", ...)
@click.pass_context
def cli(ctx, config, verbose):
    cfg = load_config(config)    # TOML + env + keyring
    setup_logging(...)
    ensure_schema(cfg.core.library_db)
```

Five subcommands registered: artist, album, library, daemon, shell.

### artist (`artist.py`)

| Command | Function |
|---------|----------|
| `add <name>` | Create artist in DB, optionally monitored |
| `list` | Table of all artists (with --monitored / --unmonitored filters) |
| `remove <id>` | Delete artist (CASCADE deletes albums/tracks) |
| `monitor <id>` | Enable monitoring |
| `unmonitor <id>` | Disable monitoring |

### album (`album.py`)

| Command | Function |
|---------|----------|
| `list` | Table of all albums (filter by --artist, --status) |
| `search <query>` | Deezer search → rich Table of results |
| `download <album_id>` | Download by DB id, process tracks, optional lyrics embedding |
| `fetch <query>` | One-step: search → add artist/album → download → process |

### library (`library.py`)

| Command | Function |
|---------|----------|
| `status` | DB stats (artists, albums, tracks, downloaded) |
| `scan [--path]` | Walk directory, import audio files |
| `prune` | Mark DB entries as missing for deleted files |
| `import <source> [--dry-run]` | Scan a directory into DB (files stay in place) |

### daemon (`daemon.py`)

| Command | Function |
|---------|----------|
| `start [--foreground]` | Fork (Unix) or foreground (Win) + APScheduler |
| `stop` | Kill by PID (TerminateProcess on Win, SIGTERM on Unix) |
| `status` | Enabled, interval, running, PID |
| `check` | Run monitoring job immediately |

PID/lock files in `default_data_dir()`. Windows foreground-only (no fork).

### shell (`shell.py`)

Interactive REPL:
```
> JPEGMAFIA
  1. [deezer] JPEGMAFIA - LP! (2021) [18t]
  ...
# 1
  downloading JPEGMAFIA - LP!...
  done: 0/18 tracks
```

Flow per query: `Searcher.search_album()` → numbered list → user picks #
→ `StreamripBackend.get_album_info()` → add artist/album/tracks to DB
→ `StreamripBackend.download_album()` → `DownloadPipeline.process_track()`
for each result → `update_album_status()`.

---

## Entry Points & Registration

`pyproject.toml`:
```toml
[project.scripts]
rswd = "rswd.__main__:cli"

[project.entry-points."rswd.backends"]
streamrip = "rswd.backends.streamrip_:StreamripBackend"
orpheus = "rswd.backends.orpheus:OrpheusBackend"
```

---

## Testing

187 tests in 23 files under `tests/`. Conftest provides `tmp_dir`, `db_path`,
`repo`, `cli_runner` fixtures.

### Test Categories

| Area | Files | Tests | Notes |
|------|-------|-------|-------|
| Backends | `test_backends/test_base.py`, `test_streamrip.py`, `test_orpheus.py` | 24 | Config init, search delegation, album info |
| CLI | `test_cli/test_album.py`, `test_artist.py`, `test_daemon.py`, `test_library.py` | 19 | Click runner tests for each subcommand |
| Config | `test_config.py`, `test_config_advanced.py` | 25 | TOML load, env overrides, redaction, expansion |
| Database | `test_db/test_schema.py`, `test_repository.py`, `test_edge_cases.py` | 28 | Full CRUD, Unicode collation, FK cascade |
| Library | `test_library.py` | 10 | Scan, import, prune, tag parsing |
| Download | `test_download.py` | 6 | Verify, checksum, move, process_track |
| Log | `test_log.py` | 3 | Handlers, daemon mode, quiet mode |
| Main | `test_main.py` | 6 | CLI help, version |
| Metadata | `test_metadata/test_lrclib.py`, `test_lyrics.py`, `test_musicbrainz.py`, `test_replaygain.py`, `test_acoustid.py` | 37 | Fetch, embed, enrich, scan |
| Search | `test_search.py` | 11 | Deezer API mock, empty results, fallback |
| Util | `test_util.py` | 15 | Sanitize, normalize, path match |

### Running

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q --tb=short
```

Requires `pytest`, `pytest-httpx`, `pytest-asyncio`. Optional metadata tests
need `musicbrainzngs`, `pyacoustid`, `httpx`.

---

## Known Issues & Edge Cases

1. **streamrip v2.1.0 `Config()` path requirement**: Uses `BLANK_CONFIG_PATH`
   from streamrip's bundled defaults. Must disable internal DB (empty paths
   cause `AssertionError`). Missing ARL triggers Rich interactive prompt
   which crashes with `EOFError` in non-TTY contexts.

2. **Deezer API rate limits**: No built-in rate limiting on the public API.
   Searcher uses 15s timeout; HTTP errors return empty results.

3. **Windows path length**: Uses `\\?\` prefix workaround for paths > 248
   characters. Hard cap at 32767.

4. **MusicBrainz rate limit**: 1 req/s enforced by musicbrainzngs client.
   Optional dependency — all methods degrade gracefully.

5. **AcoustID**: Requires `pyacoustid` + `chromaprint` native library.
   Optional — all methods return None when unavailable.

6. **Orpheus backend**: Completely unimplemented stub. Registered only for
   future extensibility.

7. **Tidal/Qobuz/Soundcloud search**: Falls back to Deezer API. No native
   search implementations for these services yet.

8. **Daemon on Windows**: No fork() — must use `--foreground`. Process
   termination uses `TerminateProcess` (no graceful shutdown).
