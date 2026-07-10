from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from rswd.config import (
    ConfigData,
    ServiceCredentials,
    _apply_env_overrides,
    _coerce,
    _dict_to_dataclass,
    _ensure_config_permissions,
    _expand_path,
    _set_deep_attr,
    default_config_dir,
    default_data_dir,
    load_config,
    redact_sensitive,
    try_keyring_load,
)


def test_redact_sensitive_arl():
    text = 'arl = "my-secret-arl-12345"'
    result = redact_sensitive(text)
    assert "my-secret-arl-12345" not in result
    assert "<redacted>" in result


def test_redact_sensitive_password():
    text = 'password_or_token = "supersecret"'
    result = redact_sensitive(text)
    assert "supersecret" not in result
    assert "<redacted>" in result


def test_redact_sensitive_multiple():
    text = 'arl = "a"\npassword_or_token = "b"'
    result = redact_sensitive(text)
    assert "<redacted>" in result
    assert 'arl = "a"' not in result
    assert 'password_or_token = "b"' not in result


def test_redact_sensitive_no_match():
    text = "normal config data"
    result = redact_sensitive(text)
    assert result == text


def test_coerce_bool_true():
    assert _coerce("true") is True
    assert _coerce("True") is True
    assert _coerce("TRUE") is True


def test_coerce_bool_false():
    assert _coerce("false") is False


def test_coerce_int():
    assert _coerce("42") == 42


def test_coerce_float():
    assert _coerce("3.14") == 3.14


def test_coerce_string():
    assert _coerce("hello") == "hello"


def test_expand_path_expands_user():
    expanded = _expand_path("~/test")
    assert "~" not in expanded
    assert Path(expanded).is_absolute()


def test_expand_path_absolute():
    expanded = _expand_path("/absolute/path")
    assert Path(expanded).is_absolute()
    assert "absolute" in expanded


def test_set_deep_attr_simple():
    cfg = ConfigData()
    _set_deep_attr(cfg, "quality.default", 5)
    assert cfg.quality.default == 5


def test_set_deep_attr_nested():
    cfg = ConfigData()
    _set_deep_attr(cfg, "metadata.lyrics.embed", False)
    assert cfg.metadata.lyrics.embed is False


def test_set_deep_attr_invalid_path():
    cfg = ConfigData()
    _set_deep_attr(cfg, "nonexistent.key", "val")
    assert not hasattr(cfg, "nonexistent")


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("rswd_QUALITY", "3")
    monkeypatch.setenv("rswd_CODEC", "ALAC")
    monkeypatch.setenv("rswd_DOWNLOAD_PATH", "/custom/path")
    cfg = ConfigData()
    cfg = _apply_env_overrides(cfg)
    assert cfg.quality.default == 3
    assert cfg.quality.codec == "ALAC"
    assert cfg.core.download_path == "/custom/path"


def test_env_overrides_unknown_var(monkeypatch):
    monkeypatch.setenv("rswd_NONEXISTENT", "value")
    cfg = ConfigData()
    cfg = _apply_env_overrides(cfg)  # should not raise


def test_default_config_dir_not_empty():
    d = default_config_dir()
    assert d.name == "rswd"


def test_default_data_dir_not_empty():
    d = default_data_dir()
    assert d.name == "rswd"


def test_config_with_nonexistent_path():
    cfg = load_config("/tmp/nonexistent_config_xyz.toml")
    assert cfg is not None
    assert isinstance(cfg, ConfigData)


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific")
def test_config_permissions_not_set_on_windows(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[core]\ndownload_path = '/music'")
    _ensure_config_permissions(cfg_file)
    assert cfg_file.exists()


def test_keyring_load_noop():
    from unittest.mock import patch

    cfg = ConfigData()
    with patch.dict("sys.modules", {"keyring": None}):
        result = try_keyring_load(cfg)
    assert result is cfg


def test_dict_to_dataclass_handles_lists():
    data = {
        "services": {
            "qobuz": {
                "secrets": ["secret1", "secret2"],
            }
        }
    }
    cfg = _dict_to_dataclass(ConfigData, data)
    assert cfg.services.qobuz.secrets == ("secret1", "secret2")
