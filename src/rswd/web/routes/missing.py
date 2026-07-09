from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from rswd.db.repository import Repository
from rswd.search import Searcher
from rswd.web.deps import get_repo, get_templates

logger = logging.getLogger("rswd.web.missing")
router = APIRouter()


@router.get("")
async def missing_page(request: Request):
    repo = get_repo(request)
    templates = get_templates(request)
    artists = repo.list_artists()
    results: list[dict] = []
    errors: list[str] = []
    searcher = Searcher(timeout=10.0)
    repo_inner = Repository(repo.db_path)
    try:
        repo_inner.connect()
        for artist in artists:
            try:
                local_albums = repo_inner.list_albums(artist_id=artist.id)
                local_titles = {a.title.lower() for a in local_albums}
                remote = searcher.get_artist_discography(artist.name)
                missing = [
                    a for a in remote
                    if a["title"].lower() not in local_titles
                ]
                if missing:
                    results.append({
                        "artist": artist,
                        "missing": missing,
                        "total_remote": len(remote),
                        "total_local": len(local_albums),
                    })
            except Exception as e:
                errors.append(f"{artist.name}: {e}")
                logger.warning("Missing check failed for %s: %s", artist.name, e)
    finally:
        repo_inner.close()
        searcher.close()
    return templates.TemplateResponse(
        request, "missing/page.html", {"results": results, "errors": errors}
    )
