import logging
import os
import platform
import re
import stat
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar, get_origin, get_type_hints

import tomllib

logger = logging.getLogger(__name__)

SERVICE_NAME = "rswd-cli"

SENSITIVE_PATTERNS = [
    (re.compile(r"arl\s*=\s*['\"][^'\"]+['\"]"), 'arl="<redacted>"'),
    (re.compile(r"password_or_token\s*=\s*['\"][^'\"]+['\"]"), 'password_or_token="<redacted>"'),
    (re.compile(r"client_secret\s*=\s*['\"][^'\"]+['\"]"), 'client_secret="<redacted>"'),
    (re.compile(r"access_token\s*=\s*['\"][^'\"]+['\"]"), 'access_token="<redacted>"'),
    (re.compile(r"refresh_token\s*=\s*['\"][^'\"]+['\"]"), 'refresh_token="<redacted>"'),
]

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
        value = pattern.sub(replacement, value)
    return value


def _coerce(val: str, expected_type: type | None = None) -> str | int | float | bool:
    lowered = val.lower()
    if expected_type is bool or (expected_type is None and lowered in ("true", "false")):
        if lowered in ("true", "1"):
            return True
        if lowered in ("false", "0"):
            return False
    try:
        int_val = int(val)
        if expected_type is float:
            return float(int_val)
        return int_val
    except (ValueError, OverflowError):
        pass
    # Whole-number floats like "1.0" are unreachable here since int() handles them above.
    # This branch is only reached for genuinely fractional values like "1.5".
    try:
        float_val = float(val)
        return float_val
    except ValueError:
        pass
    if expected_type is not None and not isinstance(val, expected_type):
        raise ValueError(f"Expected {expected_type.__name__}, got str from {val!r}")
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
    embed: bool = True  # Future use
    prefer_synced: bool = True
    providers: tuple[str, ...] = ("lrclib",)


@dataclass
class MusicBrainzConfig:
    enrichment: bool = False
    rate_limit: float = 1.0  # Future use


@dataclass
class ReplayGainConfig:
    enabled: bool = False
    mode: str = "album"


@dataclass
class AcoustIDConfig:
    enabled: bool = False
    api_key: str = ""  # Future use


@dataclass
class MetadataConfig:
    embed_cover: bool = True  # Future use
    cover_size: int = 1400  # Future use
    min_cover_bytes: int = 30000  # Future use
    cover_fallback: bool = True  # Future use
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


_T = TypeVar("_T")


def _dict_to_dataclass(cls: type[_T], data: dict) -> _T:
    known_fields = set(cls.__dataclass_fields__.keys())  # type: ignore[attr-defined]
    hints = get_type_hints(cls)

    for key in data:
        if key not in known_fields:
            logger.warning("Unknown config key '%s' in %s", key, cls.__name__)

    kwargs: dict[str, Any] = {}
    for name, ftype in hints.items():
        if name not in data:
            continue
        val = data[name]
        if hasattr(ftype, "__dataclass_fields__"):
            if not isinstance(val, dict):
                raise ValueError(f"Expected dict for {cls.__name__}.{name}, got {type(val).__name__}")
            kwargs[name] = _dict_to_dataclass(ftype, val)
        elif get_origin(ftype) is tuple:
            if isinstance(val, str):
                kwargs[name] = (val,)
            elif isinstance(val, (list, tuple)):
                kwargs[name] = tuple(val)
            else:
                kwargs[name] = (val,)
        elif isinstance(ftype, type) and not isinstance(val, ftype):
            if isinstance(val, str):
                kwargs[name] = _coerce(val, expected_type=ftype)
            elif isinstance(val, (int, float)) and ftype is bool:
                kwargs[name] = bool(val)
            elif isinstance(val, int) and ftype is float:
                kwargs[name] = float(val)
            else:
                kwargs[name] = val
        else:
            kwargs[name] = val
    return cls(**kwargs)


def _get_field_type(config: ConfigData, dotted: str) -> type | None:
    parts = dotted.split(".")
    obj: Any = config
    for i, part in enumerate(parts):
        if i == len(parts) - 1:
            return get_type_hints(type(obj)).get(part)
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return None


def _apply_env_overrides(config: ConfigData) -> ConfigData:
    for attr, env_key in ENV_MAP.items():
        val = os.environ.get(env_key)
        if val is not None:
            expected = _get_field_type(config, attr)
            _set_deep_attr(config, attr, _coerce(val, expected_type=expected))
    return config


def _set_deep_attr(obj: Any, dotted: str, value: Any):
    parts = dotted.split(".", 1)
    if len(parts) == 1:
        if hasattr(obj, parts[0]):
            setattr(obj, parts[0], value)
        else:
            logger.warning("Config attribute path '%s' does not resolve", dotted)
    else:
        child = getattr(obj, parts[0], None)
        if child is not None:
            _set_deep_attr(child, parts[1], value)
        else:
            logger.warning("Config attribute path '%s' does not resolve", dotted)


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
    if not path:
        raise ValueError("Path must not be empty")
    return str(Path(path).expanduser().resolve())


def _ensure_config_permissions(path: Path):
    # TOCTOU: race window between stat() and chmod(); safe mitigation requires
    # atomic file creation with restrictive umask or OS-level ACLs.
    if os.name != "nt":
        try:
            current = stat.S_IMODE(path.stat().st_mode)
            if current & 0o077:
                path.chmod(0o600)
        except OSError as e:
            warnings.warn(f"Could not check/set permissions on {path}: {e}")


def try_keyring_load(config: ConfigData) -> ConfigData:
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError:
        return config
    for svc_name in ("deezer", "tidal", "qobuz", "soundcloud"):
        svc = getattr(config.services, svc_name, None)
        if svc is None:
            continue
        for attr_name in ("arl", "access_token", "refresh_token", "client_id"):
            val = keyring.get_password(f"{SERVICE_NAME}.{svc_name}", attr_name)
            if val:
                logger.warning("Loaded '%s.%s' from keyring without integrity verification", svc_name, attr_name)
                setattr(svc, attr_name, val)
    return config


def _validate_config(config: ConfigData) -> None:
    if not 1 <= config.quality.default <= 5:
        raise ValueError(f"quality.default must be 1-5, got {config.quality.default}")
    if config.quality.concurrency < 1:
        raise ValueError(f"quality.concurrency must be >= 1, got {config.quality.concurrency}")
    if config.metadata.musicbrainz.rate_limit <= 0:
        raise ValueError(f"metadata.musicbrainz.rate_limit must be > 0, got {config.metadata.musicbrainz.rate_limit}")
    if config.metadata.cover_size <= 0:
        raise ValueError(f"metadata.cover_size must be > 0, got {config.metadata.cover_size}")
    if config.daemon.check_interval_hours < 0:
        raise ValueError(f"daemon.check_interval_hours must be >= 0, got {config.daemon.check_interval_hours}")
    known_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if config.core.log_level.upper() not in known_levels:
        raise ValueError(f"core.log_level must be one of {known_levels}, got {config.core.log_level!r}")
    config.core.log_level = config.core.log_level.upper()
    known_modes = {"album", "track", "auto"}
    if config.metadata.replaygain.mode not in known_modes:
        raise ValueError(f"metadata.replaygain.mode must be one of {known_modes}, got {config.metadata.replaygain.mode!r}")


def load_config(config_path: str | None = None) -> ConfigData:
    if config_path is None:
        config_path = str(default_config_dir() / "config.toml")
    cfg_path = Path(config_path)
    defaults = ConfigData()
    raw: dict = {}
    if cfg_path.is_file():
        try:
            raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Invalid config file: {e}") from e
        _ensure_config_permissions(cfg_path)
    config = _dict_to_dataclass(ConfigData, raw)
    _apply_env_overrides(config)
    config.core.download_path = _expand_path(config.core.download_path)
    config.core.library_db = _expand_path(config.core.library_db)
    config.core.jobs_db = _expand_path(config.core.jobs_db)
    config = try_keyring_load(config)
    _validate_config(config)
    return config
