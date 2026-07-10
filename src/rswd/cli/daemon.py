from __future__ import annotations

import logging
import os
import signal
import sys
import time
import datetime
from pathlib import Path

import click

from rswd.config import default_data_dir, default_config_dir
from rswd.db.repository import Repository
from rswd.log import setup_logging

logger = logging.getLogger("rswd.cli.daemon")


def _pid_path() -> Path:
    return default_data_dir() / "daemon.pid"


def _is_running() -> bool:
    pid_file = _pid_path()
    if not pid_file.is_file():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        if sys.platform == "win32":
            import ctypes
            PROCESS_QUERY_INFORMATION = 0x0400
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, 0, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, ImportError):
        return False


def _cleanup_pid():
    try:
        _pid_path().unlink(missing_ok=True)
    except Exception:
        pass


def _check_monitored_artists(repo: Repository) -> dict:
    from rswd.search import Searcher

    artists = repo.list_artists(monitored_only=True)
    # Intentionally uses a separate connection for the scheduler log to avoid
    # interfering with the main repository transaction scope.
    import sqlite3
    log_conn = sqlite3.connect(repo.db_path)
    log_conn.execute(
        "INSERT INTO scheduler_log (job_name, started_at, status) VALUES (?, ?, ?)",
        ("check_new_releases", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "running"),
    )
    log_id = log_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    results = {"artists_checked": 0, "albums_found": 0, "errors": 0}
    searcher = Searcher()

    try:
        for artist in artists:
            try:
                results["artists_checked"] += 1
                # TODO: use artist discography lookup instead of generic search_album
                # to find all releases by this specific artist
                hits = searcher.search_album(artist.name)
                for hit in hits:
                    if not repo.album_exists(artist.id, hit.title, hit.year):
                        if hit.service_id:
                            repo.add_album(
                                artist_id=artist.id,
                                title=hit.title,
                                year=hit.year,
                                total_tracks=hit.track_count,
                                service=hit.service,
                                service_id=hit.service_id,
                                quality_tier=artist.monitor_quality,
                            )
                            results["albums_found"] += 1
                            logger.info("New album for %s: %s (%s)", artist.name, hit.title, hit.year)
            except Exception as e:
                logger.warning("Error checking artist %s: %s", artist.name, e)
                results["errors"] += 1
    finally:
        searcher.close()

    log_conn.execute(
        """UPDATE scheduler_log SET completed_at = ?, status = ?, message = ?,
           albums_found = ? WHERE id = ?""",
        (
            datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "completed",
            f"Checked {results['artists_checked']} artists, found {results['albums_found']} new",
            results["albums_found"],
            log_id,
        ),
    )
    log_conn.commit()
    log_conn.close()

    return results


@click.group()
def daemon():
    """Manage the monitoring daemon."""


@daemon.command("start")
@click.option("--foreground", is_flag=True, help="Run in foreground")
@click.pass_context
def daemon_start(ctx: click.Context, foreground: bool):
    """Start the monitoring daemon."""
    config = ctx.obj["config"]

    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    if _is_running():
        click.echo("Daemon is already running.")
        return

    _pid_path().parent.mkdir(parents=True, exist_ok=True)

    if not foreground:
        if sys.platform != "win32":
            pid = os.fork()
            if pid > 0:
                click.echo(f"Daemon started (PID {pid}), interval={config.daemon.check_interval_hours}h")
                return
        else:
            click.echo("Foreground mode required on Windows. Use --foreground.")
            return

    try:
        if sys.platform == "win32":
            import msvcrt
            # Note: msvcrt.locking only locks the first n bytes; locking 1 byte
            # is sufficient here as a mutex guard for the PID file.
            pid_fd = os.open(str(_pid_path()), os.O_RDWR | os.O_CREAT | os.O_EXCL)
        else:
            import fcntl
            pid_fd = os.open(str(_pid_path()), os.O_RDWR | os.O_CREAT | os.O_EXCL)
        try:
            if sys.platform == "win32":
                msvcrt.locking(pid_fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(pid_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.write(pid_fd, str(os.getpid()).encode())
        except (OSError, PermissionError):
            os.close(pid_fd)
            click.echo("Daemon is already running.")
            return
        os.close(pid_fd)
    except FileExistsError:
        click.echo("Daemon is already running.")
        return

    log_dir = default_config_dir() / "log"
    setup_logging(log_dir, level=config.core.log_level, daemon_mode=True)

    repo = None
    try:
        from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]

        repo = Repository(config.core.library_db)

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            _check_monitored_artists,
            "interval",
            hours=config.daemon.check_interval_hours,
            args=[repo],
            id="check_new_releases",
        )

        if config.daemon.check_at_startup:
            click.echo("Running initial check...")
            _check_monitored_artists(repo)

        scheduler.start()
        click.echo(f"Daemon running (PID {os.getpid()}), checking every {config.daemon.check_interval_hours}h")

        try:
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown(wait=True)
    finally:
        if repo is not None:
            repo.close()
        _cleanup_pid()


@daemon.command("stop")
def daemon_stop():
    """Stop the running daemon."""
    pid_file = _pid_path()
    if not pid_file.is_file():
        click.echo("Daemon is not running.")
        return
    try:
        pid = int(pid_file.read_text().strip())
        if sys.platform == "win32":
            import ctypes
            PROCESS_TERMINATE = 0x0001
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, 0, pid)
            if handle:
                ctypes.windll.kernel32.TerminateProcess(handle, 0)
                ctypes.windll.kernel32.CloseHandle(handle)
                time.sleep(0.5)
            else:
                click.echo(f"PID {pid} is not running.")
                _cleanup_pid()
                return
        else:
            os.kill(pid, signal.SIGTERM)
        _cleanup_pid()
        click.echo(f"Daemon (PID {pid}) stopped.")
    except (OSError, ValueError) as e:
        click.echo(f"Failed to stop daemon: {e}")
        _cleanup_pid()


@daemon.command("status")
@click.pass_context
def daemon_status(ctx: click.Context):
    """Show daemon status."""
    config = ctx.obj["config"]
    running = _is_running()
    click.echo(f"Enabled:     {config.daemon.enabled}")
    click.echo(f"Interval:    {config.daemon.check_interval_hours}h")
    click.echo(f"Running:     {'yes' if running else 'no'}")
    if running:
        pid_file = _pid_path()
        if pid_file.is_file():
            click.echo(f"PID:         {pid_file.read_text().strip()}")


@daemon.command("check")
@click.pass_context
def daemon_check(ctx: click.Context):
    """Run the monitoring check immediately."""
    config = ctx.obj["config"]
    repo = Repository(config.core.library_db)
    with repo:
        click.echo("Checking monitored artists for new releases...")
        results = _check_monitored_artists(repo)
        click.echo(f"Artists checked: {results['artists_checked']}")
        click.echo(f"New albums found: {results['albums_found']}")
        click.echo(f"Errors: {results['errors']}")
