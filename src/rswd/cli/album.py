from __future__ import annotations

import logging
import shutil
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
    with Searcher() as searcher:
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

        quality_tier = quality if quality is not None else (album.quality_tier if album.quality_tier is not None else config.quality.default)
        output_dir = Path(config.core.download_path) / "tmp" / f"album_{album_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        service = album.service or "deezer"
        service_id = (album.service_id or "").strip()
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
        except NotImplementedError as e:
            click.echo(f"Download backend for '{service}' not fully implemented yet.")
            click.echo(f"  Would download {service}/{service_id} @ q{quality_tier}")
            logger.warning("Download not implemented for %s/%s: %s", service, service_id, e)
            return
        except Exception as e:
            click.echo(f"Download failed for '{service}': {e}")
            logger.warning("Download failed for %s/%s: %s", service, service_id, e)
            return

        pipeline = DownloadPipeline(config, repo)
        lyricist = LyricsEnricher(
            prefer_synced=config.metadata.lyrics.prefer_synced
        ) if lyrics else None

        success_count = 0
        try:
            for result in results:
                if not result.success:
                    click.echo(f"  FAIL: track {result.track_info.track_number} - {result.error}")
                    continue
                if result.file_path is None:
                    click.echo(f"  FAIL: track {result.track_info.track_number} - no file path")
                    continue

                existing_tracks = repo.list_tracks(album.id)
                track_exists = any(
                    t.track_number == result.track_info.track_number
                    and t.disc_number == (result.track_info.disc_number or 1)
                    for t in existing_tracks
                )
                if track_exists:
                    click.echo(f"  SKIP: track {result.track_info.track_number} already exists")
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
                    if lyricist and dest.suffix.lower() in (".flac", ".mp3", ".m4a", ".ogg", ".opus"):
                        lyricist.fetch_and_embed(
                            str(dest),
                            result.track_info.title,
                            result.track_info.artist,
                            album.title,
                        )
        finally:
            if lyricist:
                lyricist.close()

        if len(results) == 0:
            status = "failed"
        elif success_count == len(results):
            status = "complete"
        else:
            status = "partial"
        repo.update_album_status(
            album.id,
            status,
            quality_tier=quality_tier,
        )

        click.echo(f"Downloaded {success_count}/{len(results)} tracks.")

        shutil.rmtree(output_dir, ignore_errors=True)


@album.command("fetch")
@click.argument("query")
@click.option("--service", default="deezer", help="Service to use (deezer, tidal)")
@click.option("--quality", type=int, default=None, help="Quality tier override")
@click.option("--lyrics/--no-lyrics", default=True, help="Embed lyrics after download")
@click.pass_context
def album_fetch(ctx: click.Context, query: str, service: str, quality: int | None, lyrics: bool):
    """Search, add to library, and download an album in one step."""
    config = ctx.obj["config"]
    repo = Repository(config.core.library_db)

    with Searcher() as searcher:
        results = searcher.search_album(query, service=service)

    try:
        if not results:
            click.echo("No results found.")
            return

        hit = results[0]
        click.echo(f"Found: {hit.artist} - {hit.title} ({hit.year or '????'}) [{hit.service}]")

        artist = repo.get_artist_by_name(hit.artist)
        if not artist:
            aid = repo.add_artist(name=hit.artist, is_monitored=False)
            artist = repo.get_artist(aid)
        if not artist:
            click.echo("Failed to create artist.")
            return
        click.echo(f"Artist: '{artist.name}' (id={artist.id})")

        album_id = None
        # TODO: album_exists does exact title+year match; may miss variant titles or re-releases
        if repo.album_exists(artist.id, hit.title, hit.year):
            for a in repo.list_albums(artist_id=artist.id):
                if a.title.lower() == hit.title.lower():
                    album_id = a.id
                    click.echo(f"Album already exists (id={album_id})")
                    break

        if album_id is None:
            alid = repo.add_album(
                artist_id=artist.id,
                title=hit.title,
                year=hit.year,
                album_type=getattr(hit, 'hit_type', None) or "album",
                service=hit.service,
                service_id=hit.service_id,
            )
            if alid is None or alid == -1:
                click.echo("Failed to add album to library.")
                return
            album_id = alid
            click.echo(f"Added album '{hit.title}' (id={album_id})")

        ctx.invoke(album_download, album_id=album_id, quality=quality, lyrics=lyrics)
    finally:
        repo.close()
