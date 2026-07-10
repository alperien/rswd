from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class SearchResult:
    service: str
    media_type: str
    service_id: str
    title: str
    artists: tuple[str, ...]
    year: Optional[int] = None
    duration_s: Optional[int] = None
    track_count: Optional[int] = None
    cover_url: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrackInfo:
    service: str
    service_id: str
    title: str
    artist: str
    album: str
    album_id: str
    track_number: int
    disc_number: int = 1
    duration_s: Optional[float] = None
    isrc: Optional[str] = None
    explicit: bool = False
    file_format: Optional[str] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    bit_depth: Optional[int] = None


@dataclass(frozen=True)
class AlbumInfo:
    service: str
    service_id: str
    title: str
    artist: str
    year: Optional[int] = None
    tracks: tuple[TrackInfo, ...] = ()
    cover_url: Optional[str] = None
    label: Optional[str] = None
    upc: Optional[str] = None
    total_tracks: Optional[int] = None
    total_discs: Optional[int] = None
    explicit: bool = False


@dataclass
class DownloadResult:
    track_info: TrackInfo
    file_path: Optional[Path]
    success: bool
    error: Optional[str] = None


class SearchDownloadBackend(ABC):
    @abstractmethod
    def search(
        self, media_type: str, query: str, limit: int = 10
    ) -> list[SearchResult]:
        ...

    @abstractmethod
    def search_artist_discography(
        self, artist_name: str
    ) -> dict[str, list[AlbumInfo]]:
        ...

    @abstractmethod
    def get_album_info(self, service: str, service_id: str) -> AlbumInfo:
        ...

    @abstractmethod
    def download_album(
        self,
        service: str,
        service_id: str,
        album_info: AlbumInfo,
        output_dir: Path,
        quality: int = 2,
        codec: Optional[str] = None,
    ) -> list[DownloadResult]:
        ...

    @abstractmethod
    def login_and_validate(self) -> dict[str, bool]:
        ...
