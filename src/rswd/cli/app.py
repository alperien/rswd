from __future__ import annotations

import logging
from pathlib import Path

import click

from rswd.config import load_config, default_config_dir, default_data_dir
from rswd.db.schema import ensure_schema
from rswd.log import setup_logging

logger = logging.getLogger("rswd.cli")


@click.group()
@click.option("--config", "-c", default=None, help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, config: str | None, verbose: bool):
    """rswd-cli: Automated music library manager.

    Manages artist subscriptions and downloads from streaming services.
    """
    ctx.ensure_object(dict)
    cfg = load_config(config)
    ctx.obj["config"] = cfg

    log_dir = default_config_dir() / "log"
    setup_logging(log_dir, cfg.core.log_level, verbose)

    db_path = cfg.core.library_db
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    ensure_schema(db_path)


from rswd.cli.artist import artist  # noqa: E402
from rswd.cli.album import album  # noqa: E402
from rswd.cli.library import library  # noqa: E402
from rswd.cli.daemon import daemon  # noqa: E402
from rswd.cli.serve import serve  # noqa: E402
from rswd.cli.shell import shell  # noqa: E402

cli.add_command(artist)
cli.add_command(album)
cli.add_command(library)
cli.add_command(daemon)
cli.add_command(serve)
cli.add_command(shell)
