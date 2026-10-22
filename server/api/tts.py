"""Voice model status and download, voice list, previews, and the audio cache."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from ..schemas import ModelStatusOut
from ..state import AppState, get_state
from ..tts import EngineNotReady

log = logging.getLogger("aloud.api")
router = APIRouter(prefix="/api/tts", tags=["tts"])


@router.get("/status", response_model=ModelStatusOut)
def model_status(state: AppState = Depends(get_state)) -> dict[str, Any]:
    return state.manager.status.to_dict()


@router.post("/download", response_model=ModelStatusOut)
def start_download(state: AppState = Depends(get_state)) -> dict[str, Any]:
    return state.manager.start().to_dict()


@router.get("/voices")
def list_voices(state: AppState = Depends(get_state)) -> dict[str, Any]:
    return {
        "state": state.manager.status.state,
        "voices": [voice.to_dict() for voice in state.synth.voices()],
    }


@router.get("/preview")
async def preview_voice(
    voice: str = Query(..., max_length=64),
    text: str | None = Query(default=None, max_length=300),
    state: AppState = Depends(get_state),
) -> FileResponse:
    try:
        resolved = state.synth.resolve_voice(voice)
        sample = (text or "").strip() or state.synth.preview_text(resolved)
        path = await state.synth.render(sample, resolved)
    except EngineNotReady as error:
        raise HTTPException(503, f"Natural voices are not ready ({error})") from error
    except Exception as error:
        log.exception("Preview failed for %s", voice)
        raise HTTPException(500, f"Synthesis failed: {error}") from error
    return FileResponse(path, media_type="audio/wav")


@router.get("/cache")
def cache_stats(state: AppState = Depends(get_state)) -> dict[str, int]:
    return state.cache.stats()


@router.delete("/cache")
def clear_cache(state: AppState = Depends(get_state)) -> dict[str, int]:
    removed = state.cache.clear()
    return {"removed": removed, **state.cache.stats()}
