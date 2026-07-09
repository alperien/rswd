from __future__ import annotations

import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from rswd.backends.streamrip_ import StreamripBackend
from rswd.db.repository import Repository
from rswd.download import DownloadPipeline
from rswd.metadata.lyrics import LyricsEnricher
from rswd.search import Searcher

logger = logging.getLogger("rswd.cli.album")
console = Console()


@click.group()
def album():
    """Manage albums."""


@album.command("list")
@click.option("--artist", "artist_id", type=int, default=None, help="Filter by artist ID")
@click.option("--status", type=click.Choice(["none", "partial", "complete", "upgradable"]), default=None)
@click.pass_context
def album_list(ctx: click.Context, artist_id: int | None, status: str | None):
    """List albums in the library."""
    config = ctx.obj["config"]
    repo = Repository(config.core.library_db)
    with repo:
        albums = repo.list_albums(artist_id=artist_id, status=status)
        if not albums:
            click.echo("No albums found.")
            return
        table = Table("ID", "Artist ID", "Title", "Year", "Type", "Status", "Quality", "Service")
        for a in albums:
            table.add_row(
                str(a.id),
                str(a.artist_id),
                a.title,
                str(a.year or ""),
                a.album_type or "",
                a.download_status,
                str(a.quality_tier or ""),
                a.service or "",
            )
        console.print(table)


@album.command("search")
@click.argument("query")
@click.option("--service", default="deezer", help="Service to search (deezer, tidal)")
@click.pass_context
def album_search(ctx: click.Context, query: str, service: str):
    """Search for albums across streaming services."""
    searcher = Searcher()
    try:
        results = searcher.search_album(query, service=service)
        if not results:
            click.echo("No results found.")
            return
        table = Table("#", "Service", "Album", "Artist", "Year", "Tracks", "ID")
        for i, hit in enumerate(results, 1):
            table.add_row(
                str(i),
                hit.service,
                hit.title,
                hit.artist,
                str(hit.year or ""),
                str(hit.track_count or ""),
                hit.service_id,
            )
        console.print(table)
    finally:
        searcher.close()


@album.command("download")
@click.argument("album_id", type=int)
@click.option("--quality", type=int, default=None, help="Quality tier override")
@click.option("--lyrics/--no-lyrics", default=True, help="Embed lyrics after download")
@click.pass_context
def album_download(ctx: click.Context, album_id: int, quality: int | None, lyrics: bool):
    """Download an album and register in the library."""
    config = ctx.obj["config"]
    repo = Repository(config.core.library_db)
    with repo:
        album = repo.get_album(album_id)
        if not album:
            click.echo(f"Album id={album_id} not found.")
            return
        artist = repo.get_artist(album.artist_id)
        if not artist:
            click.echo(f"Artist id={album.artist_id} not found.")
            return

        click.echo(f"Downloading '{album.title}' by {artist.name}...")

        backend = StreamripBackend(config)

        quality_tier = quality or album.quality_tier or config.quality.default
        output_dir = Path(config.core.download_path) / "tmp" / f"album_{album_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        service = album.service or "deezer"
        service_id = album.service_id or ""
        if not service_id:
            click.echo("Album has no service_id. Search for it first, then set service_id.")
            return

        album_info = backend.get_album_info(service, service_id)

        try:
            results = backend.download_album(
                service=service,
                service_id=service_id,
                album_info=album_info,
                output_dir=output_dir,
                quality=quality_tier,
                codec=config.quality.codec or None,
            )
        except NotImplementedError:
            click.echo(f"Download backend for '{service}' not fully implemented yet. Using stub.")
            click.echo(f"  Would download {service}/{service_id} @ q{quality_tier}")
            click.echo(f"  Output would be moved to library after download.")
            return

        pipeline = DownloadPipeline(config, repo)
        lyricist = LyricsEnricher(
            prefer_synced=config.metadata.lyrics.prefer_synced
        ) if lyrics else None

        success_count = 0
        for result in results:
            if not result.success:
                click.echo(f"  FAIL: track {result.track_info.track_number} - {result.error}")
                continue
            track_id = repo.add_track(
                album_id=album.id,
                title=result.track_info.title,
                track_number=result.track_info.track_number,
                disc_number=result.track_info.disc_number,
                duration=result.track_info.duration_s,
                artist=result.track_info.artist,
                isrc=result.track_info.isrc,
            )
            dest = pipeline.process_track(
                source=result.file_path,
                album_id=album.id,
                track_id=track_id,
                album_artist=artist.name,
                album_title=album.title,
                year=album.year,
                track_num=result.track_info.track_number,
                track_artist=result.track_info.artist,
                track_title=result.track_info.title,
                service=service,
                quality=quality_tier,
            )
            if dest:
                success_count += 1
                if lyricist and dest.suffix.lower() in (".flac", ".mp3"):
                    lyricist.fetch_and_embed(
                        str(dest),
                        result.track_info.title,
                        result.track_info.artist,
                        album.title,
                    )

        repo.update_album_status(
            album.id,
            "complete" if success_count == len(results) else "partial",
            quality_tier=quality_tier,
        )

        click.echo(f"Downloaded {success_count}/{len(results)} tracks.")

        if lyricist:
            lyricist.close()
