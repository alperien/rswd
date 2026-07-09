from __future__ import annotations

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from rswd.config import ConfigData as Config
from rswd.db.repository import Repository
from rswd.web.routes import library, search, monitor, queue, daemon, import_, missing, config_


HERE = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    config: Config = app.state.config
    app.state.repo = Repository(config.core.library_db)
    yield


def create_app(config: Config) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.state.config = config

    templates = Jinja2Templates(directory=str(HERE / "templates"))
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    app.include_router(library.router, prefix="/library", tags=["library"])
    app.include_router(search.router, prefix="/search", tags=["search"])
    app.include_router(monitor.router, prefix="/monitor", tags=["monitor"])
    app.include_router(queue.router, prefix="/queue", tags=["queue"])
    app.include_router(daemon.router, prefix="/daemon", tags=["daemon"])
    app.include_router(import_.router, prefix="/import", tags=["import"])
    app.include_router(missing.router, prefix="/missing", tags=["missing"])
    app.include_router(config_.router, prefix="/config", tags=["config"])

    @app.get("/")
    async def root():
        return RedirectResponse(url="/library")

    return app
