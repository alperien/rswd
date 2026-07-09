from __future__ import annotations

from fastapi import APIRouter, Request

from rswd.web.deps import get_repo, get_templates
from rswd.web.download_manager import DlStatus, DownloadManager

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
