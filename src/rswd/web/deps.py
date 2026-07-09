from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates

from rswd.db.repository import Repository


def get_repo(request: Request) -> Repository:
    return request.app.state.repo


def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates
