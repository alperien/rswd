from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rswd.search import Searcher
from rswd.web.deps import get_templates

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
