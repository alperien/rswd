from __future__ import annotations

import platform
import re
import sys
import unicodedata
from pathlib import Path

MAX_PATH = 260 if sys.platform == "win32" else 4096

_FS_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*]')
_FS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}


def sanitize_filename(name: str, max_len: int = 200) -> str:
    if max_len < 1:
        raise ValueError(f"max_len must be at least 1, got {max_len}")
    name = name.replace("\x00", "")
    name = _FS_ILLEGAL_CHARS.sub("", name).strip()
    name = re.sub(r"[\s.]+$", "", name)
    if sys.platform == "win32" and name.lower() in _FS_RESERVED_NAMES:
        name = f"_{name}"
    if len(name) > max_len:
        base, _, ext = name.rpartition(".")
        if ext and len(ext) < 10:
            name = base[: max_len - len(ext) - 1] + "." + ext
        else:
            name = name[:max_len]
    return name if name else "_"


def normalize_name(name: str, filesystem: bool = False) -> str:
    nfc = unicodedata.normalize("NFC", name.strip())
    if filesystem and sys.platform == "darwin":
        return unicodedata.normalize("NFD", nfc)
    return nfc


def paths_match(db_path: str, fs_path: str) -> bool:
    form = "NFD" if sys.platform == "darwin" else "NFC"
    a = unicodedata.normalize(form, db_path)
    b = unicodedata.normalize(form, fs_path)
    if sys.platform in ("win32", "darwin"):
        return a.casefold() == b.casefold()
    return a == b


def validate_path_length(path: Path) -> Path:
    try:
        resolved = path.resolve()
    except OSError:
        if sys.platform == "win32":
            resolved = Path("\\\\?\\") / path.absolute()
        else:
            raise
    else:
        if sys.platform == "win32" and len(str(resolved)) > MAX_PATH - 12:
            resolved = Path("\\\\?\\") / resolved
    if len(str(resolved)) > 32767:
        raise OSError(f"Path too long: {resolved}")
    return resolved


def platform_label() -> str:
    system = platform.system()
    if system == "Darwin":
        return "macos"
    elif system == "Windows":
        return "windows"
    return "linux"
