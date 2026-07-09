from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from rswd.config import default_config_dir, load_config, redact_sensitive, ConfigData
from rswd.web.deps import get_templates

router = APIRouter()


@router.get("")
async def config_page(request: Request):
    templates = get_templates(request)
    cfg: ConfigData = request.app.state.config
    return templates.TemplateResponse(request, "config/page.html", {
        "cfg": cfg,
        "config_path": str(default_config_dir() / "config.toml"),
    })
