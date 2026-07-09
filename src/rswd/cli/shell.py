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

        searcher = Searcher()
        try:
            results = searcher.search_album(query)
        finally:
            searcher.close()

        if not results:
            print("  no results")
            continue

        for i, r in enumerate(results, 1):
            yr = r.year or "????"
            tc = r.track_count or "?"
            print(f"  {i:2d}. [{r.service}] {r.artist} - {r.album} ({yr}) [{tc}t]")

        try:
            sel = input("  # ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not sel.isdigit() or int(sel) < 1 or int(sel) > len(results):
            continue

        hit = results[int(sel) - 1]
        print(f"  downloading {hit.artist} - {hit.album}...")

        repo = Repository(config.core.library_db)
        backend = StreamripBackend(config)

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
            ) or 0
        if not album_id:
            print("  failed: could not create album")
            continue

        info = backend.get_album_info(hit.service, hit.service_id)
        download_path = Path(config.core.download_path) / "incoming" / hit.service_id

        track_map: dict[int, int] = {}
        for t in info.tracks:
            tid = repo.add_track(
                album_id=album_id, title=t.title,
                track_number=t.track_number, disc_number=t.disc_number,
                duration=t.duration_s, artist=t.artist,
            )
            track_map[t.track_number] = tid

        results_dl = backend.download_album(hit.service, hit.service_id, info, download_path)
        pipeline = DownloadPipeline(config, repo)

        done = 0
        for r_dl in results_dl:
            tn = r_dl.track_info.track_number
            matched_tid = track_map.get(tn)
            if r_dl.success and r_dl.file_path.exists() and matched_tid is not None:
                try:
                    pipeline.process_track(
                        source=r_dl.file_path, album_id=album_id, track_id=matched_tid,
                        album_artist=hit.artist, album_title=hit.title,
                        year=hit.year, track_num=tn,
                        track_artist=r_dl.track_info.artist,
                        track_title=r_dl.track_info.title, service=hit.service,
                    )
                    done += 1
                except Exception as e:
                    print(f"  error on track {tn}: {e}")

        if done:
            repo.update_album_status(album_id, "downloaded")

        print(f"  done: {done}/{len(results_dl)} tracks")
