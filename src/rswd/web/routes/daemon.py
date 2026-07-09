from __future__ import annotations

from fastapi import APIRouter, Request

from rswd.web.deps import get_templates

router = APIRouter()


@router.get("")
async def daemon_page(request: Request):
    templates = get_templates(request)
    return templates.TemplateResponse(
        request, "daemon/page.html", {"logs": [], "running": False}
    )
