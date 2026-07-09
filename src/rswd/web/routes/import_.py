from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from rswd.library import LibraryScanner
from rswd.web.deps import get_repo, get_templates

router = APIRouter()


@router.get("")
async def import_page(request: Request):
    templates = get_templates(request)
    return templates.TemplateResponse(request, "import/page.html")


@router.post("")
async def import_scan(request: Request, source: str = Form("")):
    repo = get_repo(request)
    templates = get_templates(request)
    if not source.strip():
        return templates.TemplateResponse(
            request, "import/results.html",
            {"error": "Please provide a directory path"},
        )
    scanner = LibraryScanner(repo)
    stats = scanner.scan_directory(source)
    pruned = scanner.prune_missing()
    return templates.TemplateResponse(
        request, "import/results.html",
        {"stats": stats, "pruned": pruned, "source": source},
    )
