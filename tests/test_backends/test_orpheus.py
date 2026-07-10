from __future__ import annotations

import pytest

from rswd.backends.orpheus import OrpheusBackend


def test_orpheus_init():
    backend = OrpheusBackend()
    assert backend._config == {}


def test_orpheus_init_with_config():
    backend = OrpheusBackend({"install_path": "/opt/orpheus"})
    assert backend._config["install_path"] == "/opt/orpheus"


def test_orpheus_search_returns_empty():
    backend = OrpheusBackend()
    assert backend.search("album", "test") == []


def test_orpheus_discography_returns_empty():
    backend = OrpheusBackend()
    assert backend.search_artist_discography("test") == {}


def test_orpheus_download_not_implemented(tmp_path):
    backend = OrpheusBackend()
    with pytest.raises(NotImplementedError):
        backend.download_album("deezer", "123", None, tmp_path)


def test_orpheus_album_info_not_implemented():
    backend = OrpheusBackend()
    with pytest.raises(NotImplementedError):
        backend.get_album_info("deezer", "123")


def test_orpheus_login_and_validate():
    backend = OrpheusBackend()
    with pytest.raises(NotImplementedError):
        backend.login_and_validate()
