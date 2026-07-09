from pathlib import Path

import pytest

from rswd.config import ConfigData, default_config_dir, load_config


def test_default_config_has_minimal_values():
    cfg = load_config("/nonexistent/config.toml")
    assert "music" in cfg.core.download_path.lower()
    assert cfg.quality.default == 2
    assert cfg.backend.name == "streamrip"


def test_default_config_dir_is_absolute():
    d = default_config_dir()
    assert isinstance(d, Path)
    assert d.is_absolute()


def test_config_overrides_via_env(monkeypatch):
    monkeypatch.setenv("rswd_QUALITY", "3")
    monkeypatch.setenv("rswd_LOG_LEVEL", "DEBUG")
    cfg = load_config("/nonexistent/config.toml")
    assert cfg.quality.default == 3
    assert cfg.core.log_level == "DEBUG"
