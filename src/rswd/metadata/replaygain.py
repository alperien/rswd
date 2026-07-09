from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

import mutagen

logger = logging.getLogger("rswd.metadata.replaygain")




class ReplayGainScanner:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self._ffmpeg = ffmpeg_path

    def _parse_ebur128_output(self, text: str) -> dict[str, float]:
        integrated = None
        peak = None
        for line in text.splitlines():
            line = line.strip()
            m = re.match(r"I:\s+([-\d.]+)\s+dB", line)
            if m:
                integrated = float(m.group(1))
            m = re.match(r"Peak:\s+([-\d.]+)\s+dBFS", line)
            if m:
                peak = float(m.group(1))
        return {"track_gain": integrated, "track_peak": peak}  # type: ignore[dict-item]

    def scan_file(self, file_path: str) -> Optional[dict[str, float]]:
        try:
            result = subprocess.run(
                [self._ffmpeg, "-i", file_path, "-af", "ebur128", "-f", "null", "-"],
                capture_output=True, text=True, timeout=120,
            )
            return self._parse_ebur128_output(result.stderr)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("ReplayGain scan failed for %s: %s", file_path, e)
            return None

    def write_track_gain(self, file_path: str, gain: float, peak: float) -> bool:
        try:
            audio = mutagen.File(file_path)
            if audio is None:
                return False
            tags = audio.tags
            if tags is None:
                audio.add_tags()
                tags = audio.tags
            if isinstance(tags, mutagen.id3.ID3):
                from mutagen.id3 import TXXX
                tags.delall("TXXX:REPLAYGAIN_TRACK_GAIN")
                tags.delall("TXXX:REPLAYGAIN_TRACK_PEAK")
                tags.add(TXXX(encoding=3, desc="REPLAYGAIN_TRACK_GAIN",
                              text=f"{gain:.2f} dB"))
                tags.add(TXXX(encoding=3, desc="REPLAYGAIN_TRACK_PEAK",
                              text=f"{peak:.6f}"))
            else:
                tags["REPLAYGAIN_TRACK_GAIN"] = f"{gain:.2f} dB"
                tags["REPLAYGAIN_TRACK_PEAK"] = f"{peak:.6f}"
            audio.save()
            logger.info("Wrote ReplayGain tags to %s", file_path)
            return True
        except Exception as e:
            logger.warning("Failed to write ReplayGain tags to %s: %s", file_path, e)
            return False

    def scan_and_embed(self, file_path: str) -> bool:
        rg = self.scan_file(file_path)
        if rg is None or rg["track_gain"] is None:
            return False
        return self.write_track_gain(file_path, rg["track_gain"], rg["track_peak"] or 0.0)
