from __future__ import annotations

from fastapi import APIRouter, Request

from rswd.web.deps import get_repo, get_templates

router = APIRouter()


@router.get("")
async def queue_page(request: Request):
    repo = get_repo(request)
    templates = get_templates(request)
    with repo as r:
        stats = r.library_stats()
    return templates.TemplateResponse(
        request, "queue/page.html", {"stats": stats}
    )
