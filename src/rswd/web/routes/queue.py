from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from rswd.web.deps import get_repo, get_templates
from rswd.web.download_manager import DlStatus, DownloadManager

router = APIRouter()


@router.get("/")
async def queue_page(request: Request):
    repo = get_repo(request)
    templates = get_templates(request)
    with repo as r:
        stats = r.library_stats()
    return templates.TemplateResponse(
        request, "queue/page.html", {"stats": stats}
    )


@router.get("/tasks")
async def list_tasks(request: Request):
    templates = get_templates(request)
    mgr: DownloadManager = request.app.state.download_manager
    tasks = mgr.list_tasks()
    return templates.TemplateResponse(
        request, "queue/_tasks.html", {"tasks": tasks}
    )


@router.get("/task/{task_id}/status")
async def task_status(request: Request, task_id: str):
    templates = get_templates(request)
    mgr: DownloadManager = request.app.state.download_manager
    task = mgr.get_task(task_id)
    if task is None:
        return templates.TemplateResponse(
            request, "queue/_task_status.html",
            {"task": None, "task_id": task_id},
        )
    return templates.TemplateResponse(
        request, "queue/_task_status.html",
        {"task": task, "task_id": task_id},
    )


@router.get("/stream")
async def queue_stream(request: Request):
    mgr: DownloadManager = request.app.state.download_manager

    async def event_stream():
        q = await mgr.subscribe()
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            mgr.unsubscribe(q)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
