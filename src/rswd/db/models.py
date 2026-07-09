from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Artist:
    id: int = 0
    name: str = ""
    sort_name: Optional[str] = None
    mb_artistid: Optional[str] = None
    is_monitored: bool = False
    monitor_quality: int = 2
    added_at: str = ""
    metadata_blob: Optional[str] = None


@dataclass
class Album:
    id: int = 0
    artist_id: int = 0
    title: str = ""
    year: Optional[int] = None
    album_type: Optional[str] = None
    mb_albumid: Optional[str] = None
    mb_release_groupid: Optional[str] = None
    total_tracks: Optional[int] = None
    download_status: str = "none"
    quality_tier: Optional[int] = None
    service: Optional[str] = None
    service_id: Optional[str] = None
    added_at: str = ""
    metadata_blob: Optional[str] = None


@dataclass
class Track:
    id: int = 0
    album_id: int = 0
    title: str = ""
    track_number: Optional[int] = None
    disc_number: int = 1
    duration: Optional[float] = None
    artist: Optional[str] = None
    file_path: Optional[str] = None
    file_format: Optional[str] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    bit_depth: Optional[int] = None
    isrc: Optional[str] = None
    mb_recording_id: Optional[str] = None
    service_id: Optional[str] = None
    download_status: str = "pending"
    added_at: str = ""


@dataclass
class DownloadLogEntry:
    id: int = 0
    track_id: int = 0
    service: str = ""
    quality: Optional[int] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    checksum: Optional[str] = None
    downloaded_at: str = ""


@dataclass
class SchedulerLogEntry:
    id: int = 0
    job_name: str = ""
    started_at: str = ""
    completed_at: Optional[str] = None
    status: str = ""
    message: Optional[str] = None
    albums_found: int = 0
    tracks_added: int = 0
    tracks_dled: int = 0
