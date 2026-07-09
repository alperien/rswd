import os
import platform
import re
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib

SERVICE_NAME = "rswd-cli"

SENSITIVE_PATTERNS = [
    (r'arl\s*=\s*"[^"]+"', 'arl="<redacted>"'),
    (r'password_or_token\s*=\s*"[^"]+"', 'password_or_token="<redacted>"'),
    (r'client_secret\s*=\s*"[^"]+"', 'client_secret="<redacted>"'),
    (r'access_token\s*=\s*"[^"]+"', 'access_token="<redacted>"'),
    (r'refresh_token\s*=\s*"[^"]+"', 'refresh_token="<redacted>"'),
]

ENV_PREFIX = "rswd_"
ENV_MAP: dict[str, str] = {
    "core.download_path": "rswd_DOWNLOAD_PATH",
    "quality.default": "rswd_QUALITY",
    "quality.codec": "rswd_CODEC",
    "core.log_level": "rswd_LOG_LEVEL",
    "services.deezer.arl": "rswd_DEEZER_ARL",
    "services.tidal.access_token": "rswd_TIDAL_ACCESS_TOKEN",
    "quality.concurrency": "rswd_CONCURRENCY",
    "daemon.check_interval_hours": "rswd_DAEMON_INTERVAL",
}


def redact_sensitive(value: str) -> str:
    for pattern, replacement in SENSITIVE_PATTERNS:
        value = re.sub(pattern, replacement, value)
    return value


def _coerce(val: str) -> str | int | float | bool:
    lowered = val.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def default_config_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "rswd"
    elif system == "Windows":
        return Path(os.environ.get("APPDATA", Path.home() / ".config")) / "rswd"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "rswd"


@dataclass
class CoreConfig:
    download_path: str = "~/music"
    library_db: str = ""
    jobs_db: str = ""
    log_level: str = "INFO"

    def __post_init__(self):
        if not self.library_db:
            self.library_db = str(default_data_dir() / "library.db")
        if not self.jobs_db:
            self.jobs_db = str(default_data_dir() / "jobs.db")


@dataclass
class DaemonConfig:
    enabled: bool = False
    check_interval_hours: int = 24
    check_at_startup: bool = True


@dataclass
class QualityConfig:
    default: int = 2
    codec: str = ""
    concurrency: int = 3


@dataclass
class FilepathsConfig:
    album_folder: str = "{albumartist}/{album} ({year})"
    track_file: str = "{tracknum:02d}. {artist} - {title}{ext}"


@dataclass
class LyricsConfig:
    embed: bool = True
    prefer_synced: bool = True
    providers: tuple[str, ...] = ("lrclib",)


@dataclass
class MusicBrainzConfig:
    enrichment: bool = False
    rate_limit: float = 1.0


@dataclass
class ReplayGainConfig:
    enabled: bool = False
    mode: str = "album"


@dataclass
class AcoustIDConfig:
    enabled: bool = False
    api_key: str = ""


@dataclass
class MetadataConfig:
    embed_cover: bool = True
    cover_size: int = 1400
    min_cover_bytes: int = 30000
    cover_fallback: bool = True
    lyrics: LyricsConfig = field(default_factory=LyricsConfig)
    musicbrainz: MusicBrainzConfig = field(default_factory=MusicBrainzConfig)
    replaygain: ReplayGainConfig = field(default_factory=ReplayGainConfig)
    acoustid: AcoustIDConfig = field(default_factory=AcoustIDConfig)


@dataclass
class StreamripBackendConfig:
    config_path: str = ""


@dataclass
class OrpheusDLConfig:
    install_path: str = ""


@dataclass
class BackendConfig:
    name: str = "streamrip"
    streamrip: StreamripBackendConfig = field(default_factory=StreamripBackendConfig)
    orpheusdl: OrpheusDLConfig = field(default_factory=OrpheusDLConfig)


@dataclass
class ServiceCredentials:
    arl: str = ""
    access_token: str = ""
    refresh_token: str = ""
    user_id: str = ""
    country_code: str = ""
    token_expiry: str = ""
    email_or_userid: str = ""
    password_or_token: str = ""
    app_id: str = ""
    secrets: tuple[str, ...] = ()
    client_id: str = ""
    app_version: str = ""


@dataclass
class ServicesConfig:
    deezer: ServiceCredentials = field(default_factory=ServiceCredentials)
    tidal: ServiceCredentials = field(default_factory=ServiceCredentials)
    qobuz: ServiceCredentials = field(default_factory=ServiceCredentials)
    soundcloud: ServiceCredentials = field(default_factory=ServiceCredentials)


@dataclass
class ConfigData:
    core: CoreConfig = field(default_factory=CoreConfig)
    daemon: DaemonConfig = field(default_factory=DaemonConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    filepaths: FilepathsConfig = field(default_factory=FilepathsConfig)
    metadata: MetadataConfig = field(default_factory=MetadataConfig)
    backend: BackendConfig = field(default_factory=BackendConfig)
    services: ServicesConfig = field(default_factory=ServicesConfig)


def _dict_to_dataclass(cls: type, data: dict) -> Any:
    field_types = {f.name: f.type for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    kwargs: dict[str, Any] = {}
    for name, ftype in field_types.items():
        if name not in data:
            continue
        val = data[name]
        if hasattr(ftype, "__dataclass_fields__"):
            kwargs[name] = _dict_to_dataclass(ftype, val)
        elif isinstance(val, list):
            kwargs[name] = tuple(val)
        else:
            kwargs[name] = val
    return cls(**kwargs)


def _apply_env_overrides(config: ConfigData) -> ConfigData:
    for attr, env_key in ENV_MAP.items():
        val = os.environ.get(env_key)
        if val is not None:
            _set_deep_attr(config, attr, _coerce(val))
    return config


def _set_deep_attr(obj: Any, dotted: str, value: Any):
    parts = dotted.split(".", 1)
    if len(parts) == 1:
        if hasattr(obj, parts[0]):
            setattr(obj, parts[0], value)
    else:
        child = getattr(obj, parts[0], None)
        if child is not None:
            _set_deep_attr(child, parts[1], value)


def default_data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "rswd"
    elif system == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "rswd"
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data) / "rswd"
    return Path.home() / ".local" / "share" / "rswd"


def _expand_path(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def _ensure_config_permissions(path: Path):
    if os.name != "nt":
        current = stat.S_IMODE(path.stat().st_mode)
        if current & 0o077:
            path.chmod(0o600)


def try_keyring_load(config: ConfigData) -> ConfigData:
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError:
        return config
    for svc_name in ("deezer", "tidal", "qobuz", "soundcloud"):
        svc = getattr(config.services, svc_name, None)
        if svc is None:
            continue
        for field in ("arl", "access_token", "refresh_token", "client_id"):
            val = keyring.get_password(f"{SERVICE_NAME}.{svc_name}", field)
            if val:
                setattr(svc, field, val)
    return config


def load_config(config_path: str | None = None) -> ConfigData:
    if config_path is None:
        config_path = str(default_config_dir() / "config.toml")
    cfg_path = Path(config_path)
    defaults = ConfigData()
    raw: dict = {}
    if cfg_path.is_file():
        raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        _ensure_config_permissions(cfg_path)
    config = _dict_to_dataclass(ConfigData, raw)
    _apply_env_overrides(config)
    if not config.core.library_db:
        config.core.library_db = str(default_data_dir() / "library.db")
    if not config.core.jobs_db:
        config.core.jobs_db = str(default_data_dir() / "jobs.db")
    config.core.download_path = _expand_path(config.core.download_path)
    config.core.library_db = _expand_path(config.core.library_db)
    config.core.jobs_db = _expand_path(config.core.jobs_db)
    config = try_keyring_load(config)
    return config
