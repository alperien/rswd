from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from rswd.scheduler import get_state, start, stop
from rswd.web.deps import get_templates

router = APIRouter()


@router.get("/")
async def daemon_page(request: Request):
    templates = get_templates(request)
    state = get_state()
    return templates.TemplateResponse(
        request, "daemon/page.html",
        {
            "running": state.running,
            "started_at": state.started_at or "",
            "logs": state.logs[-100:],
        },
    )


@router.post("/start")
async def daemon_start(request: Request):
    start()
    return RedirectResponse(url="/daemon", status_code=303)


@router.post("/stop")
async def daemon_stop(request: Request):
    stop()
    return RedirectResponse(url="/daemon", status_code=303)
