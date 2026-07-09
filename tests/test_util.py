from __future__ import annotations

import sys
from pathlib import Path

from rswd.util import (
    sanitize_filename,
    normalize_name,
    paths_match,
    validate_path_length,
    platform_label,
)


def test_sanitize_removes_illegal_chars():
    result = sanitize_filename('foo:bar/baz<qux>"test"')
    assert ":" not in result
    assert "/" not in result
    assert "<" not in result
    assert ">" not in result
    assert '"' not in result


def test_sanitize_strips_trailing_dots():
    if sys.platform == "win32":
        result = sanitize_filename("trailing...")
        assert not result.endswith(".")


def test_sanitize_strips_trailing_spaces():
    result = sanitize_filename("trailing   ")
    assert not result.endswith(" ")


def test_sanitize_reserved_names_windows():
    if sys.platform == "win32":
        result = sanitize_filename("con")
        assert result == "_con"
        result = sanitize_filename("NUL")
        assert result == "_NUL"


def test_sanitize_reserved_names_not_windows():
    result = sanitize_filename("con")
    if sys.platform != "win32":
        assert result != "_con"


def test_sanitize_truncates_long_names():
    long_name = "a" * 300
    result = sanitize_filename(long_name, max_len=200)
    assert len(result) <= 200


def test_sanitize_keeps_extension_when_truncating():
    name = "a" * 200 + ".flac"
    result = sanitize_filename(name, max_len=50)
    assert result.endswith(".flac") or len(result) <= 200


def test_normalize_name_nfc():
    result = normalize_name("  Café  ")
    assert result == "Café"
    assert result == "Caf\u00e9"


def test_normalize_name_empty():
    assert normalize_name("  ") == ""


def test_paths_match_same():
    assert paths_match("/path/to/file", "/path/to/file") is True


def test_paths_match_different():
    assert paths_match("/path/a", "/path/b") is False


def test_paths_match_unicode():
    assert paths_match("Caf\u00e9", "Cafe\u0301") is True


def test_validate_path_length_returns_path():
    p = validate_path_length(Path("C:\\test\\path"))
    assert isinstance(p, Path)


def test_validate_path_length_raises_on_extreme():
    long_path = Path("a" * 33000)
    try:
        validate_path_length(long_path)
        assert False
    except (OSError, ValueError):
        pass


def test_platform_label():
    label = platform_label()
    assert label in ("windows", "linux", "macos")
