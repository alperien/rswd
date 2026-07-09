from __future__ import annotations

import logging
from typing import Optional

import mutagen

from rswd.metadata.lrclib import LRCLibProvider, LyricsResult

logger = logging.getLogger("rswd.metadata.lyrics")


class LyricsEnricher:
    def __init__(self, prefer_synced: bool = True):
        self._lrclib = LRCLibProvider()
        self.prefer_synced = prefer_synced

    def fetch_and_embed(
        self,
        file_path: str,
        track: str,
        artist: str,
        album: str | None = None,
        duration: int | None = None,
    ) -> bool:
        result = self._lrclib.fetch(track, artist, album, duration)
        if result is None:
            return False
        return self._embed_in_file(file_path, result)

    def _embed_in_file(self, file_path: str, lyrics: LyricsResult) -> bool:
        try:
            audio = mutagen.File(file_path)
            if audio is None:
                return False
            tags = audio.tags
            if tags is None:
                audio.add_tags()
                tags = audio.tags

            text = lyrics.synced if (lyrics.synced and self.prefer_synced) else lyrics.plain
            if not text:
                return False

            if isinstance(tags, mutagen.id3.ID3):
                from mutagen.id3 import USLT
                tags.delall("USLT")
                tags.add(USLT(encoding=3, text=text))
            else:
                tags["LYRICS"] = text

            audio.save()
            logger.info("Embedded lyrics in %s", file_path)
            return True
        except Exception as e:
            logger.warning("Failed to embed lyrics in %s: %s", file_path, e)
            return False

    def close(self):
        self._lrclib.close()
