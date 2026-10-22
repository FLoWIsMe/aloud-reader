"""Everything long-lived that request handlers share."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from .config import Config
from .db import Database, now_iso
from .extract import Extracted, title_from_blocks
from .segment import segment_blocks
from .tts import AudioCache, ModelManager, SynthService


@dataclass
class AppState:
    config: Config
    db: Database
    manager: ModelManager
    cache: AudioCache
    synth: SynthService

    def store_document(
        self,
        extracted: Extracted,
        source_kind: str,
        source_name: str | None,
        title: str | None = None,
    ) -> dict[str, Any]:
        segmented = segment_blocks(extracted.blocks)
        if segmented.chunk_count == 0:
            raise ValueError("No readable text was found")
        resolved_title = (title or extracted.title or title_from_blocks(extracted.blocks)).strip()
        stamp = now_iso()
        doc = {
            "id": secrets.token_hex(8),
            "title": resolved_title[:300] or "Untitled",
            "source_kind": source_kind,
            "source_name": source_name,
            "created_at": stamp,
            "updated_at": stamp,
            "last_opened_at": None,
            "word_count": segmented.word_count,
            "char_count": segmented.char_count,
            "chunk_count": segmented.chunk_count,
            "position": 0,
            "finished_at": None,
            "voice": None,
        }
        self.db.insert_document(doc, segmented.to_dicts())
        return doc


def get_state(request: Request) -> AppState:
    return request.app.state.aloud
