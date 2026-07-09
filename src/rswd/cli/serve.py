from __future__ import annotations

import webbrowser
import uvicorn

import click


@click.command("serve")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8080, type=int, help="Port to listen on")
@click.option("--open", "open_browser", is_flag=True, help="Open browser on start")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int, open_browser: bool) -> None:
    """Launch the web UI."""
    config = ctx.obj["config"]
    if open_browser:
        webbrowser.open(f"http://{host}:{port}")
    from rswd.web.app import create_app
    app = create_app(config)
    uvicorn.run(app, host=host, port=port)
