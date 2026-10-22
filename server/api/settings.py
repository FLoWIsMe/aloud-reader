"""User settings: default voice, speed, theme, and reader preferences."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..schemas import SettingsUpdate
from ..state import AppState, get_state

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULTS: dict[str, Any] = {
    "voice": "af_heart",
    "browser_voice": None,
    "speed": 1.0,
    "theme": "system",
    "autoscroll": True,
    "text_size": "medium",
}


def current_settings(state: AppState) -> dict[str, Any]:
    stored = state.db.get_settings()
    return {**DEFAULTS, **{key: value for key, value in stored.items() if key in DEFAULTS}}


@router.get("")
def get_settings(state: AppState = Depends(get_state)) -> dict[str, Any]:
    return current_settings(state)


@router.put("")
def update_settings(
    payload: SettingsUpdate, state: AppState = Depends(get_state)
) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if "speed" in changes and changes["speed"] is not None:
        changes["speed"] = round(float(changes["speed"]), 1)
    if changes:
        state.db.set_settings(changes)
    return current_settings(state)
