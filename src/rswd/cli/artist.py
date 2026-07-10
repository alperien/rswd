from __future__ import annotations

import logging

import click
from rich.console import Console
from rich.table import Table

from rswd.db.repository import Repository

logger = logging.getLogger("rswd.cli.artist")
console = Console()


@click.group()
def artist():
    """Manage artist subscriptions."""


@artist.command("add")
@click.argument("name")
@click.option("--service", default=None, help="Service to search (deezer, tidal)")
@click.option("--monitor/--no-monitor", default=True, help="Monitor for new releases")
@click.option("--quality", type=int, default=2, help="Quality tier (0=128k, 1=320k, 2=CD, 3=HiRes)")
@click.pass_context
def artist_add(ctx: click.Context, name: str, service: str | None, monitor: bool, quality: int):
    """Add an artist by name."""
    config = ctx.obj["config"]
    repo = Repository(config.core.library_db)
    try:
        existing = repo.get_artist_by_name(name)
        if existing:
            click.echo(f"Artist '{name}' already exists (id={existing.id})")
            return
        artist_id = repo.add_artist(
            name=name,
            is_monitored=monitor,
            monitor_quality=quality,
        )
        click.echo(f"Added artist '{name}' (id={artist_id}, monitored={monitor})")
        if monitor:
            click.echo("  Monitoring enabled — daemon will check for new releases.")
    finally:
        repo.close()


@artist.command("list")
@click.option("--monitored", is_flag=True, help="Show only monitored artists")
@click.option("--unmonitored", is_flag=True, help="Show only unmonitored artists")
@click.pass_context
def artist_list(ctx: click.Context, monitored: bool, unmonitored: bool):
    """List all artists."""
    config = ctx.obj["config"]
    repo = Repository(config.core.library_db)
    try:
        if monitored:
            rows = repo.list_artists(monitored_only=True)
        elif unmonitored:
            # TODO: add an unmonitored_only parameter to Repository.list_artists()
            # to avoid fetching all artists when only unmonitored ones are needed
            rows = [a for a in repo.list_artists() if not a.is_monitored]
        else:
            rows = repo.list_artists()
        if not rows:
            click.echo("No artists found.")
            return
        table = Table("ID", "Name", "Monitored", "Quality", "MBID")
        for a in rows:
            table.add_row(
                str(a.id),
                a.name,
                "yes" if a.is_monitored else "no",
                str(a.monitor_quality),
                a.mb_artistid or "",
            )
        console.print(table)
    finally:
        repo.close()


@artist.command("remove")
@click.argument("artist_id", type=int)
@click.pass_context
def artist_remove(ctx: click.Context, artist_id: int):
    """Remove an artist and all associated data."""
    config = ctx.obj["config"]
    repo = Repository(config.core.library_db)
    try:
        artist = repo.get_artist(artist_id)
        if not artist:
            click.echo(f"Artist id={artist_id} not found.")
            return
        repo.remove_artist(artist_id)
        click.echo(f"Removed artist '{artist.name}' (id={artist_id})")
    finally:
        repo.close()


@artist.command("monitor")
@click.argument("artist_id", type=int)
@click.pass_context
def artist_monitor(ctx: click.Context, artist_id: int):
    """Enable monitoring for an artist."""
    config = ctx.obj["config"]
    repo = Repository(config.core.library_db)
    try:
        if repo.set_monitored(artist_id, True):
            click.echo(f"Enabled monitoring for artist id={artist_id}")
        else:
            click.echo(f"Artist id={artist_id} not found.")
    finally:
        repo.close()


@artist.command("unmonitor")
@click.argument("artist_id", type=int)
@click.pass_context
def artist_unmonitor(ctx: click.Context, artist_id: int):
    """Disable monitoring for an artist."""
    config = ctx.obj["config"]
    repo = Repository(config.core.library_db)
    try:
        if repo.set_monitored(artist_id, False):
            click.echo(f"Disabled monitoring for artist id={artist_id}")
        else:
            click.echo(f"Artist id={artist_id} not found.")
    finally:
        repo.close()
