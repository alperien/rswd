# rswd

**CLI-based automated music library manager.** Searches streaming services
(via Deezer), downloads albums via streamrip, organizes files by
artist/album, enriches metadata (lyrics, ReplayGain, MusicBrainz IDs,
AcoustID), and runs a headless daemon for periodic new-release checks.

## Quick Start

```powershell
pip install -e ".[dev,metadata]"
$env:RSWD_DEEZER_ARL = "your_arl"
python -m rswd shell
```

## Commands

| Command | Description |
|---------|-------------|
| `artist add/list/remove/monitor/unmonitor` | Manage artist subscriptions |
| `album list/search/download <id>/fetch <query>` | Search & download albums |
| `library status/scan/prune/import` | Manage local music database |
| `daemon start/stop/status/check` | Headless new-release monitor |
| `shell` | Interactive search & download REPL |

## Features

- **Search** — Deezer album/artist search via public API
- **Download** — streamrip-backed (Deezer, Tidal, Qobuz, Soundcloud)
- **Organization** — `Artist/Album (year)/NN. Artist - Title.ext`
- **Metadata** — LRCLib lyrics, MusicBrainz MBIDs, ReplayGain (EBU R128),
  AcoustID fingerprint matching
- **Daemon** — APScheduler-based periodic check for new releases from
  monitored artists
- **Database** — SQLite with WAL mode, migration system, Unicode NOCASE
  collation, foreign keys, 6 tables
- **Config** — TOML file + environment variable overrides + keyring backend

## Documentation

Full technical docs in `docs/`:

- **`docs/architecture.md`** — Complete codebase reference: data flows,
  configuration subsystem, database schema, backend architecture,
  CLI commands, metadata pipelines, known issues
- **`docs/development.md`** — Setup guide, conventions, testing,
  extension guides

## Stack

Python 3.11+, click, rich, streamrip, mutagen, APScheduler.
Optional: musicbrainzngs, pyacoustid, httpx.

187 tests, zero mypy errors.

## License

MIT
