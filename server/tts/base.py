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
    cache_tag: str  # changes whenever the audio for the same text and voice would change

    def voices(self) -> list[Voice]: ...

    def synthesize(self, text: str, voice: str) -> np.ndarray: ...


def trim_silence(
    samples: np.ndarray,
    sample_rate: int,
    top_db: float = 40.0,
    head_ms: int = 20,
    tail_ms: int = 30,
) -> np.ndarray:
    """Cut leading and trailing near-silence, measured per 10 ms frame against the loudest.

    Keeps a small margin on both sides and fades the cut edges so there is no click.
    """
    samples = np.asarray(samples, dtype=np.float32)
    frame = max(1, sample_rate // 100)
    count = len(samples) // frame
    if count < 3:
        return samples
    rms = np.sqrt(np.mean(samples[: count * frame].reshape(count, frame) ** 2, axis=1))
    reference = float(rms.max())
    if reference <= 0:
        return samples
    loud = np.flatnonzero(rms >= reference * 10 ** (-top_db / 20))
    if len(loud) == 0:
        return samples
    start = max(0, int(loud[0]) * frame - head_ms * sample_rate // 1000)
    end = min(len(samples), (int(loud[-1]) + 1) * frame + tail_ms * sample_rate // 1000)
    trimmed = samples[start:end].copy()
    fade = min(len(trimmed) // 2, 4 * sample_rate // 1000)
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        trimmed[:fade] *= ramp
        trimmed[-fade:] *= ramp[::-1]
    return trimmed


def with_pause(samples: np.ndarray, sample_rate: int, pause_ms: int) -> np.ndarray:
    """Append `pause_ms` of silence, the gap the listener hears before the next sentence."""
    if pause_ms <= 0:
        return samples
    silence = np.zeros(pause_ms * sample_rate // 1000, dtype=np.float32)
    return np.concatenate([np.asarray(samples, dtype=np.float32), silence])


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
