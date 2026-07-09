from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from rswd.backends.streamrip_ import StreamripBackend
from rswd.config import ConfigData
from rswd.db.repository import Repository
from rswd.download import DownloadPipeline
from rswd.search import Searcher
from rswd.web.deps import get_repo, get_templates
from rswd.web.download_manager import DlStatus, DownloadManager

logger = logging.getLogger("rswd.web.search")

router = APIRouter()


@router.get("")
async def search_page(request: Request):
    templates = get_templates(request)
    return templates.TemplateResponse(request, "search/page.html")


@router.post("")
async def search_execute(request: Request, query: str = ""):
    templates = get_templates(request)
    if not query.strip():
        return templates.TemplateResponse(
            request, "search/_results.html", {"results": []}
        )
    searcher = Searcher()
    try:
        results = searcher.search_album(query)
    finally:
        searcher.close()
    return templates.TemplateResponse(
        request, "search/_results.html", {"results": results}
    )


@router.post("/download/{service}/{service_id}")
async def download_album(request: Request, service: str, service_id: str):
    templates = get_templates(request)
    backend = StreamripBackend(request.app.state.config)
    try:
        info = backend.get_album_info(service, service_id)
    except NotImplementedError:
        return templates.TemplateResponse(
            request, "search/_results.html",
            {"results": [], "error": f"Download not supported for {service}"},
        )

    mgr: DownloadManager = request.app.state.download_manager
    task_id = mgr.create_task(service, service_id, info.title, info.artist)
    mgr.update_task(task_id, status=DlStatus.DOWNLOADING)

    config: ConfigData = request.app.state.config
    db_path = config.core.library_db
    download_path = Path(config.core.download_path) / "incoming" / task_id

    def run():
        try:
            results = backend.download_album(service, service_id, info, download_path)
            repo = Repository(db_path)
            pipeline = DownloadPipeline(config, repo)

            artist = repo.get_artist_by_name(info.artist)
            if not artist:
                aid = repo.add_artist(name=info.artist, is_monitored=False)
                artist = repo.get_artist(aid)
            if not artist:
                mgr.update_task(task_id, status=DlStatus.FAILED, error="Could not create artist in DB")
                return

            album_id = None
            for a in repo.list_albums(artist_id=artist.id):
                if a.title.lower() == info.title.lower():
                    album_id = a.id
                    break

            if album_id is None:
                alid = repo.add_album(
                    artist_id=artist.id,
                    title=info.title,
                    year=info.year,
                    album_type="album",
                    total_tracks=info.total_tracks,
                    service=service,
                    service_id=service_id,
                )
                album_id = alid

            done = 0
            errors = 0
            for result in results:
                if result.success and result.file_path.exists():
                    try:
                        pipeline.process_track(
                            source=result.file_path,
                            album_id=album_id,
                            track_id=0,
                            album_artist=info.artist,
                            album_title=info.title,
                            year=info.year,
                            track_num=result.track_info.track_number,
                            track_artist=result.track_info.artist,
                            track_title=result.track_info.title,
                            service=service,
                        )
                        done += 1
                    except Exception as e:
                        logger.exception("process_track failed: %s", e)
                        errors += 1
                else:
                    errors += 1

            if album_id:
                repo.update_album_status(album_id, "downloaded")

            mgr.update_task(
                task_id,
                status=DlStatus.COMPLETED,
                tracks_total=done + errors,
                tracks_done=done,
                progress=f"{done} tracks downloaded, {errors} errors",
            )
        except Exception as e:
            logger.exception("Download failed for task %s", task_id)
            mgr.update_task(task_id, status=DlStatus.FAILED, error=str(e))

    t = threading.Thread(target=run, daemon=True)
    t.start()

    return templates.TemplateResponse(
        request, "search/_download_status.html",
        {"task_id": task_id, "album_title": info.title, "artist_name": info.artist},
    )
