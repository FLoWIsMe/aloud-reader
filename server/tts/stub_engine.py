"""A tiny deterministic engine for tests and for running the app without any model."""

from __future__ import annotations

import numpy as np

from .base import Voice


class StubEngine:
    """Produces a short tone whose length scales with the text, so playback can be tested."""

    name = "stub"
    sample_rate = 16000

    def __init__(self) -> None:
        self._voices = [
            Voice("stub_low", "Stub Low", "stub", "en-us", "English (US)", "male", "test"),
            Voice("stub_high", "Stub High", "stub", "en-us", "English (US)", "female", "test"),
        ]

    @property
    def loaded(self) -> bool:
        return True

    def load(self) -> None:
        return None

    def voices(self) -> list[Voice]:
        return list(self._voices)

    def has_voice(self, voice_id: str) -> bool:
        return any(voice.id == voice_id for voice in self._voices)

    def synthesize(self, text: str, voice: str) -> np.ndarray:
        words = max(1, len(text.split()))
        seconds = min(4.0, 0.12 * words + 0.1)
        frequency = 440.0 if voice == "stub_high" else 220.0
        t = np.arange(int(seconds * self.sample_rate), dtype=np.float32) / self.sample_rate
        envelope = np.minimum(1.0, 20.0 * np.minimum(t, seconds - t))
        return (0.2 * np.sin(2 * np.pi * frequency * t) * envelope).astype(np.float32)
