from __future__ import annotations

import logging

import click
from rich.console import Console

from rswd.db.repository import Repository
from rswd.library import LibraryScanner

logger = logging.getLogger("rswd.cli.library")
console = Console()


@click.group()
def library():
    """Library management commands."""


@library.command("status")
@click.pass_context
def library_status(ctx: click.Context):
    """Show library statistics."""
    config = ctx.obj["config"]
    repo = Repository(config.core.library_db)
    with repo:
        stats = repo.library_stats()
        click.echo(f"Artists:    {stats['artists']}")
        click.echo(f"Albums:     {stats['albums']}")
        click.echo(f"Tracks:     {stats['tracks']}")
        click.echo(f"Downloaded: {stats['downloaded']}")
        click.echo(f"DB path:    {config.core.library_db}")
        click.echo(f"Download:   {config.core.download_path}")


@library.command("scan")
@click.option("--path", default=None, help="Directory to scan (default: download_path)")
@click.pass_context
def library_scan(ctx: click.Context, path: str | None):
    """Scan a directory for music files and import into the database."""
    config = ctx.obj["config"]
    scan_path = path or config.core.download_path
    click.echo(f"Scanning {scan_path}...")
    repo = Repository(config.core.library_db)
    with repo:
        scanner = LibraryScanner(repo)
        stats = scanner.scan_directory(scan_path)
        click.echo(f"Scanned:  {stats['scanned']}")
        click.echo(f"Matched:  {stats['matched']}")
        click.echo(f"Imported: {stats['imported']}")
        click.echo(f"Errors:   {stats['errors']}")


@library.command("prune")
@click.pass_context
def library_prune(ctx: click.Context):
    """Mark database entries as missing for files that no longer exist."""
    config = ctx.obj["config"]
    repo = Repository(config.core.library_db)
    with repo:
        scanner = LibraryScanner(repo)
        removed = scanner.prune_missing()
        click.echo(f"Pruned {removed} missing tracks.")


@library.command("import")
@click.argument("source", type=click.Path(exists=True, file_okay=False))
@click.option("--dry-run", is_flag=True, help="Show what would be imported without importing")
@click.pass_context
def library_import(ctx: click.Context, source: str, dry_run: bool):
    """Import an existing music library directory into the database.

    Walks SOURCE directory, reads audio metadata tags, and creates
    artist/album/track entries in the database. Files are NOT moved.
    """
    config = ctx.obj["config"]
    repo = Repository(config.core.library_db)
    with repo:
        scanner = LibraryScanner(repo)
        if dry_run:
            click.echo(f"Dry-run scan of {source}...")
            stats = scanner.scan_directory(source)
            click.echo(f"Would scan:  {stats['scanned']}")
            click.echo(f"Would import: {stats['imported']}")
            click.echo(f"Already matched: {stats['matched']}")
            return

        click.echo(f"Importing from {source}...")
        stats = scanner.scan_directory(source)
        click.echo(f"Scanned:  {stats['scanned']}")
        click.echo(f"Imported: {stats['imported']}")
        click.echo(f"Matched:  {stats['matched']}")
        click.echo(f"Errors:   {stats['errors']}")
