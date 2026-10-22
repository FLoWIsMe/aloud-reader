"""Shared types for text-to-speech engines."""

from __future__ import annotations

import io
import wave
from dataclasses import asdict, dataclass
from typing import Any, Protocol

import numpy as np


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    engine: str
    language: str
    language_name: str
    gender: str
    quality: str = "standard"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Engine(Protocol):
    """Anything that can turn a sentence into mono float32 samples."""

    name: str
    sample_rate: int

    def voices(self) -> list[Voice]: ...

    def synthesize(self, text: str, voice: str) -> np.ndarray: ...


def encode_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Encode float32 samples in [-1, 1] as 16-bit PCM WAV."""
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


def wav_duration_seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data), "rb") as handle:
        frames = handle.getnframes()
        rate = handle.getframerate() or 1
    return frames / rate
