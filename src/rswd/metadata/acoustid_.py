from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("rswd.metadata.acoustid")


class AcoustIDMatcher:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def fingerprint(self, file_path: str) -> Optional[str]:
        try:
            import acoustid  # type: ignore[import-untyped]
            duration, fp = acoustid.fingerprint_file(file_path)
            logger.debug("Fingerprinted %s: duration=%s", file_path, duration)
            return fp
        except ImportError:
            logger.warning("pyacoustid not installed, skipping fingerprint")
            return None
        except Exception as e:
            logger.warning("Fingerprinting failed for %s: %s", file_path, e)
            return None

    def lookup(self, file_path: str) -> Optional[dict]:
        fp = self.fingerprint(file_path)
        if fp is None:
            return None
        try:
            import acoustid  # type: ignore[import-untyped]
            data = acoustid.lookup(self._api_key, fp)
            for result in data.get("results", []):
                score = result.get("score", 0)
                if score > 0.5:
                    recordings = result.get("recordings", [])
                    if recordings:
                        rec = recordings[0]
                        artists = rec.get("artists", [])
                        artist_name = artists[0].get("name", "") if artists else ""
                        return {
                            "mb_recording_id": rec.get("id"),
                            "title": rec.get("title"),
                            "artist": artist_name,
                            "score": score,
                        }
            return None
        except Exception as e:
            logger.warning("AcoustID lookup failed for %s: %s", file_path, e)
            return None
