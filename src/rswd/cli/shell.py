from __future__ import annotations

import sys
from pathlib import Path

import click

from rswd.backends.streamrip_ import StreamripBackend
from rswd.config import ConfigData
from rswd.db.repository import Repository
from rswd.download import DownloadPipeline
from rswd.search import Searcher


@click.command("shell")
@click.pass_context
def shell(ctx: click.Context):
    """Interactive search & download shell."""
    config: ConfigData = ctx.obj["config"]

    try:
        searcher = Searcher()
        repo = Repository(config.core.library_db)
        backend = StreamripBackend(config)
    except Exception as e:
        click.echo(f"Failed to initialize: {e}")
        return

    try:
        while True:
            try:
                query = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not query:
                continue
            if query in ("exit", "quit", "q"):
                break

            try:
                results = searcher.search_album(query)
            except Exception as e:
                print(f"  search error: {e}")
                continue

            if not results:
                print("  no results")
                continue

            for i, r in enumerate(results, 1):
                yr = r.year or "????"
                tc = r.track_count or "?"
                print(f"  {i:2d}. [{r.service}] {r.artist} - {r.album or r.title} ({yr}) [{tc}t]")

            try:
                sel = input("  # ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not sel.isdigit() or int(sel) < 1 or int(sel) > len(results):
                continue

            hit = results[int(sel) - 1]
            print(f"  downloading {hit.artist} - {hit.album or hit.title}...")

            artist_obj = repo.get_artist_by_name(hit.artist)
            if not artist_obj:
                aid = repo.add_artist(name=hit.artist, is_monitored=False)
                artist_obj = repo.get_artist(aid)
            if not artist_obj:
                print("  failed: could not create artist")
                continue

            existing = [a for a in repo.list_albums(artist_id=artist_obj.id)
                        if a.title.lower() == hit.title.lower()]
            if existing:
                album_id = existing[0].id
            else:
                album_id = repo.add_album(
                    artist_id=artist_obj.id, title=hit.title, year=hit.year,
                    album_type="album", service=hit.service, service_id=hit.service_id,
                )
            if album_id is None or album_id == -1:
                print("  failed: could not create album")
                continue

            try:
                info = backend.get_album_info(hit.service, hit.service_id)
            except Exception as e:
                print(f"  error fetching album info: {e}")
                continue

            download_path = Path(config.core.download_path) / "incoming" / hit.service_id
            download_path.mkdir(parents=True, exist_ok=True)

            track_map: dict[tuple[int, int], int] = {}
            existing_tracks = repo.list_albums(artist_id=artist_obj.id)
            for et in repo.list_tracks(album_id):
                if et.track_number is not None:
                    track_map[(et.disc_number, et.track_number)] = et.id

            results_dl = backend.download_album(hit.service, hit.service_id, info, download_path)
            pipeline = DownloadPipeline(config, repo)

            done = 0
            failed = 0
            for r_dl in results_dl:
                tn = r_dl.track_info.track_number
                dn = r_dl.track_info.disc_number or 1
                if not r_dl.success or r_dl.file_path is None or not r_dl.file_path.is_file():
                    print(f"  FAIL: track {tn} - {r_dl.error or 'download failed'}")
                    failed += 1
                    continue
                matched_tid = track_map.get((dn, tn))
                if matched_tid is None:
                    tid = repo.add_track(
                        album_id=album_id, title=r_dl.track_info.title,
                        track_number=tn, disc_number=dn,
                        duration=r_dl.track_info.duration_s, artist=r_dl.track_info.artist,
                        isrc=r_dl.track_info.isrc,
                    )
                    track_map[(dn, tn)] = tid
                    matched_tid = tid
                try:
                    proc_result = pipeline.process_track(
                        source=r_dl.file_path, album_id=album_id, track_id=matched_tid,
                        album_artist=hit.artist, album_title=hit.album or hit.title,
                        year=hit.year, track_num=tn,
                        track_artist=r_dl.track_info.artist,
                        track_title=r_dl.track_info.title, service=hit.service,
                    )
                    if proc_result is not None:
                        done += 1
                    else:
                        print(f"  FAIL: track {tn} - processing returned None")
                        failed += 1
                except Exception as e:
                    print(f"  error on track {tn}: {e}")
                    failed += 1

            if done:
                repo.update_album_status(album_id, "complete")

            status_msg = f"  done: {done}/{len(results_dl)} tracks"
            if failed:
                status_msg += f" ({failed} failed)"
            print(status_msg)
    finally:
        searcher.close()
        repo.close()
        try:
            backend.close()
        except Exception:
            pass
