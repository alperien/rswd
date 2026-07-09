from __future__ import annotations

from unittest.mock import patch

import pytest

from rswd.metadata.acoustid_ import AcoustIDMatcher


def test_fingerprint_calls_acoustid(tmp_path):
    f = tmp_path / "test.flac"
    f.write_bytes(b"fake audio data")
    matcher = AcoustIDMatcher(api_key="test-key")
    with patch("acoustid.fingerprint_file") as mock_fp:
        mock_fp.return_value = (120.0, "fp12345")
        result = matcher.fingerprint(str(f))
        assert result == "fp12345"
        mock_fp.assert_called_once_with(str(f))


def test_fingerprint_returns_none_on_import_error(tmp_path):
    f = tmp_path / "test.flac"
    f.write_bytes(b"data")
    matcher = AcoustIDMatcher(api_key="test-key")
    with patch.dict("sys.modules", {"acoustid": None}):
        pass
    result = matcher.fingerprint(str(f))
    assert result is None


def test_fingerprint_returns_none_on_exception(tmp_path):
    f = tmp_path / "test.flac"
    f.write_bytes(b"data")
    matcher = AcoustIDMatcher(api_key="test-key")
    with patch("acoustid.fingerprint_file") as mock_fp:
        mock_fp.side_effect = Exception("fingerprint error")
        result = matcher.fingerprint(str(f))
        assert result is None


def test_lookup_returns_high_score_match(tmp_path):
    f = tmp_path / "test.flac"
    f.write_bytes(b"data")
    matcher = AcoustIDMatcher(api_key="test-key")
    with patch.object(matcher, "fingerprint") as mock_fp:
        mock_fp.return_value = "fp123"
        with patch("acoustid.lookup") as mock_lookup:
            mock_lookup.return_value = {
                "results": [
                    {
                        "id": 1,
                        "score": 0.9,
                        "recordings": [
                            {
                                "id": "mbid-123",
                                "title": "Song",
                                "artists": [{"name": "Artist"}],
                            }
                        ],
                    }
                ]
            }
            result = matcher.lookup(str(f))
            assert result is not None
            assert result["mb_recording_id"] == "mbid-123"
            assert result["score"] == 0.9


def test_lookup_returns_none_on_low_score(tmp_path):
    f = tmp_path / "test.flac"
    f.write_bytes(b"data")
    matcher = AcoustIDMatcher(api_key="test-key")
    with patch.object(matcher, "fingerprint") as mock_fp:
        mock_fp.return_value = "fp123"
        with patch("acoustid.lookup") as mock_lookup:
            mock_lookup.return_value = {
                "results": [
                    {
                        "id": 1,
                        "score": 0.3,
                        "recordings": [
                            {
                                "id": "mbid-456",
                                "title": "Song",
                                "artists": [{"name": "Artist"}],
                            }
                        ],
                    }
                ]
            }
            result = matcher.lookup(str(f))
            assert result is None


def test_lookup_returns_none_when_fingerprint_fails(tmp_path):
    f = tmp_path / "test.flac"
    f.write_bytes(b"data")
    matcher = AcoustIDMatcher(api_key="test-key")
    with patch.object(matcher, "fingerprint") as mock_fp:
        mock_fp.return_value = None
        result = matcher.lookup(str(f))
        assert result is None


def test_lookup_handles_exception(tmp_path):
    f = tmp_path / "test.flac"
    f.write_bytes(b"data")
    matcher = AcoustIDMatcher(api_key="test-key")
    with patch.object(matcher, "fingerprint") as mock_fp:
        mock_fp.return_value = "fp123"
        with patch("acoustid.lookup") as mock_lookup:
            mock_lookup.side_effect = Exception("lookup error")
            result = matcher.lookup(str(f))
            assert result is None
