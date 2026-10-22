"""Serializes synthesis on one worker and dedupes identical in-flight requests."""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from ..config import Config
from .base import Voice, encode_wav
from .cache import AudioCache
from .kokoro_engine import PREVIEW_TEXT
from .manager import ModelManager

log = logging.getLogger("aloud.tts")


class EngineNotReady(RuntimeError):
    pass


class SynthService:
    def __init__(self, config: Config, manager: ModelManager, cache: AudioCache) -> None:
        self.config = config
        self.manager = manager
        self.cache = cache
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aloud-synth")
        self._inflight: dict[str, Future] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def voices(self) -> list[Voice]:
        engine = self.manager.engine
        return engine.voices() if engine else []

    def default_voice(self) -> str | None:
        voices = self.voices()
        return voices[0].id if voices else None

    def resolve_voice(self, voice: str | None) -> str:
        engine = self.manager.engine
        if engine is None:
            raise EngineNotReady(self.manager.status.state)
        if voice and engine.has_voice(voice):
            return voice
        return self.default_voice() or ""

    def preview_text(self, voice: str) -> str:
        engine = self.manager.engine
        if engine is None:
            raise EngineNotReady(self.manager.status.state)
        for info in engine.voices():
            if info.id == voice:
                return PREVIEW_TEXT.get(info.language, PREVIEW_TEXT["en-us"])
        return PREVIEW_TEXT["en-us"]

    def render_sync(self, text: str, voice: str) -> Path:
        """Return the cached WAV for this sentence, synthesizing it if needed. Blocking."""
        engine = self.manager.engine
        if engine is None:
            raise EngineNotReady(self.manager.status.state)
        voice = self.resolve_voice(voice)
        key = AudioCache.key(engine.name, voice, text)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        with self._lock:
            future = self._inflight.get(key)
            if future is None:
                future = self._executor.submit(self._synthesize_and_store, key, text, voice)
                self._inflight[key] = future
        try:
            return future.result()
        finally:
            with self._lock:
                if self._inflight.get(key) is future:
                    del self._inflight[key]

    async def render(self, text: str, voice: str) -> Path:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.render_sync, text, voice)

    def _synthesize_and_store(self, key: str, text: str, voice: str) -> Path:
        engine = self.manager.engine
        if engine is None:
            raise EngineNotReady(self.manager.status.state)
        samples = engine.synthesize(text, voice)
        data = encode_wav(samples, engine.sample_rate)
        return self.cache.put(key, data)
