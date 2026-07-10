from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger("rswd.metadata.acoustid")


class AcoustIDMatcher:
    MIN_SCORE = 0.5

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
        except (
            IOError, OSError, ValueError, LookupError,
            acoustid.FingerprintGenerationError, acoustid.WebServiceError,
        ) as e:
            logger.warning("Fingerprinting failed for %s: %s", file_path, e)
            return None

    def lookup(self, file_path: str) -> Optional[dict]:
        fp = self.fingerprint(file_path)
        if fp is None:
            return None
        for attempt in range(3):
            try:
                import acoustid  # type: ignore[import-untyped]
                data = acoustid.lookup(self._api_key, fp)
                results = data.get("results", [])
                if not results:
                    return None
                best = max(results, key=lambda r: r.get("score", 0))
                score = best.get("score", 0)
                if score <= self.MIN_SCORE:
                    return None
                recordings = best.get("recordings", [])
                if not recordings:
                    return None
                rec = recordings[0]
                artists = rec.get("artists", [])
                artist_name = artists[0].get("name", "") if artists else ""
                return {
                    "mb_recording_id": rec.get("id"),
                    "title": rec.get("title"),
                    "artist": artist_name,
                    "score": score,
                }
            except (
                IOError, OSError, ValueError, LookupError,
                acoustid.FingerprintGenerationError, acoustid.WebServiceError,
            ) as e:
                if attempt < 2:
                    time.sleep(1)
                    continue
                logger.warning("AcoustID lookup failed for %s: %s", file_path, e)
                return None
