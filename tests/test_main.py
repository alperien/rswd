from __future__ import annotations

from click.testing import CliRunner

from rswd.__main__ import cli


def test_cli_no_args_shows_help():
    runner = CliRunner()
    result = runner.invoke(cli, [])
    assert result.exit_code == 2  # Click shows usage error when no command given
    assert "Usage:" in result.output or "Error" in result.output


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_help_artists():
    runner = CliRunner()
    result = runner.invoke(cli, ["artist", "--help"])
    assert result.exit_code == 0
    assert "Manage artist subscriptions" in result.output


def test_cli_help_albums():
    runner = CliRunner()
    result = runner.invoke(cli, ["album", "--help"])
    assert result.exit_code == 0
    assert "Manage albums" in result.output


def test_cli_help_library():
    runner = CliRunner()
    result = runner.invoke(cli, ["library", "--help"])
    assert result.exit_code == 0
    assert "Library management" in result.output


def test_cli_help_daemon():
    runner = CliRunner()
    result = runner.invoke(cli, ["daemon", "--help"])
    assert result.exit_code == 0
    assert "Manage the monitoring daemon" in result.output
