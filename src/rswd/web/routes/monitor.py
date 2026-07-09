from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rswd.web.deps import get_repo, get_templates

router = APIRouter()


@router.get("/")
async def monitor_page(request: Request):
    repo = get_repo(request)
    templates = get_templates(request)
    with repo as r:
        artists = r.list_artists(monitored_only=True)
    return templates.TemplateResponse(
        request, "monitor/page.html", {"artists": artists}
    )


@router.post("/{artist_id}/toggle")
async def monitor_toggle(request: Request, artist_id: int):
    repo = get_repo(request)
    with repo as r:
        artist = r.get_artist(artist_id)
        if artist:
            r.set_monitored(artist_id, not artist.is_monitored)
    return RedirectResponse(url="/monitor", status_code=303)
