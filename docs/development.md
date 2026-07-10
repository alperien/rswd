# Development Guide

## Setup

```powershell
git clone <repo>
cd rswd
python -m venv .venv
.venv\Scripts\Activate
pip install -e ".[dev,metadata]"
```

Dependencies (see `pyproject.toml`):
- **Runtime**: click, rich, apscheduler, streamrip, mutagen
- **Metadata opt-in**: musicbrainzngs, pyacoustid, httpx
- **Dev**: pytest, pytest-cov, pytest-httpx, pytest-asyncio, vcrpy

## Running

```powershell
# CLI
$env:PYTHONPATH = "src"
python -m rswd --help

# Interactive shell
python -m rswd shell

# Daemon
python -m rswd daemon start --foreground
```

## Testing

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q --tb=short
python -m pytest -q --tb=short -k "test_search"  # specific module
python -m pytest -q --tb=short --cov=rswd         # with coverage
```

## Type Checking

```powershell
$env:PYTHONPATH = "src"
python -m mypy src/rswd/
```

Zero errors is the target. The only allowed notes are `annotation-unchecked`
on untyped callbacks.

## Code Conventions

- `from __future__ import annotations` in every file
- All dataclasses are frozen where immutable semantics apply
- Backend backends register via entry points (extensible)
- Context managers for Repository lifecycle
- Logging via `logging.getLogger("rswd.<module>")`
- No comments in code (documentation lives in docs/)
- Sanitize all user/filename input before filesystem operations
- Catch broad exceptions at module boundaries, log, return graceful defaults

## Adding a New Streaming Service

1. Add credentials to `ServiceCredentials` in `config.py`
2. Add ENV_MAP entry in `config.py`
3. Add handling in `_configdata_to_dict()` and `_build_rp_config()` in `streamrip_.py`
4. Add search method in `search.py` (or fall back to existing)
5. Add `get_album_info` handling in `streamrip_.py`

## Adding a New CLI Command

1. Create file in `rswd/cli/`
2. Define `@click.group()` or `@click.command()`
3. Import and register in `cli/app.py`
4. Add tests in `tests/test_cli/`

## Deployment

```powershell
# As a daemon process
python -m rswd daemon start --foreground
```

## Versioning

Current: 0.1.0 (alpha). Follows semantic versioning.
Breaking streamrip API changes may cause bumps.
