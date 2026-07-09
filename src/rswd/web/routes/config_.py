from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from rswd.config import default_config_dir, ConfigData
from rswd.web.deps import get_templates

router = APIRouter()


@router.get("/")
async def config_page(request: Request):
    templates = get_templates(request)
    cfg: ConfigData = request.app.state.config
    return templates.TemplateResponse(request, "config/page.html", {
        "cfg": cfg,
        "config_path": str(default_config_dir() / "config.toml"),
    })


@router.post("/save")
async def config_save(
    request: Request,
    deezer_arl: str = Form(""),
    tidal_access_token: str = Form(""),
    tidal_client_id: str = Form(""),
):
    cfg: ConfigData = request.app.state.config
    if deezer_arl and deezer_arl != "********":
        cfg.services.deezer.arl = deezer_arl
    if tidal_access_token and tidal_access_token != "********":
        cfg.services.tidal.access_token = tidal_access_token
    if tidal_client_id:
        cfg.services.tidal.client_id = tidal_client_id

    config_dir = default_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"

    def _val(v):
        if isinstance(v, str):
            return f'"{v}"'
        return str(v).lower()

    lines = [
        "[services]",
        "",
        "[services.deezer]",
        f"arl = {_val(cfg.services.deezer.arl)}",
        "",
        "[services.tidal]",
        f"access_token = {_val(cfg.services.tidal.access_token)}",
        f"client_id = {_val(cfg.services.tidal.client_id)}",
    ]
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return RedirectResponse(url="/config", status_code=303)
