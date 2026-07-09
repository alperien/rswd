from __future__ import annotations

from fastapi import APIRouter, Request

from rswd.web.deps import get_repo, get_templates

router = APIRouter()


@router.get("/")
async def library_page(request: Request):
    templates = get_templates(request)
    return templates.TemplateResponse(request, "library/browse.html")


@router.get("/artists")
async def artist_list(request: Request, filter: str = ""):
    repo = get_repo(request)
    templates = get_templates(request)
    with repo as r:
        artists = r.list_artists()
    if filter:
        lower = filter.lower()
        artists = [a for a in artists if lower in a.name.lower()]
    return templates.TemplateResponse(
        request, "library/_artists.html", {"artists": artists}
    )


@router.get("/artists/{artist_id}/albums")
async def album_grid(request: Request, artist_id: int):
    repo = get_repo(request)
    templates = get_templates(request)
    with repo as r:
        albums = r.list_albums(artist_id=artist_id)
    return templates.TemplateResponse(
        request, "library/_albums.html", {"albums": albums}
    )


@router.get("/albums/{album_id}/tracks")
async def track_table(request: Request, album_id: int):
    repo = get_repo(request)
    templates = get_templates(request)
    tracks = repo.list_tracks(album_id=album_id)
    return templates.TemplateResponse(
        request, "library/_tracks.html", {"tracks": tracks}
    )
