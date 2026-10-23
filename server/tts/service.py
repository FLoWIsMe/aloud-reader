"""One synthesis worker, two queues: the sentence someone is waiting on comes first, and the
rest of the document is warmed in the background whenever the worker is idle.

Warming is what removes the gap between sentences on a first listen. The browser tells the
server where the listener is, and the worker keeps the next `warm_ahead` sentences cached,
so by the time playback reaches them they are a file read, not a synthesis.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from .base import Voice, encode_wav
from .cache import AudioCache
from .kokoro_engine import PREVIEW_TEXT
from .manager import ModelManager

log = logging.getLogger("aloud.tts")


class EngineNotReady(RuntimeError):
    pass


@dataclass
class _Job:
    key: str
    text: str
    voice: str
    future: Future
    background: bool = False


@dataclass
class WarmPlan:
    document_id: str
    voice: str
    chunks: list[str]
    cursor: int  # where the listener is
    next_index: int  # next chunk to look at
    limit: int  # how far past the cursor to go

    @property
    def end(self) -> int:
        return min(len(self.chunks), self.cursor + self.limit)

    def has_work(self) -> bool:
        return self.next_index < self.end


class SynthService:
    def __init__(self, config: Config, manager: ModelManager, cache: AudioCache) -> None:
        self.config = config
        self.manager = manager
        self.cache = cache
        self._live: deque[_Job] = deque()
        self._inflight: dict[str, Future] = {}
        self._plan: WarmPlan | None = None
        self._cv = threading.Condition()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, name="aloud-synth", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        with self._cv:
            self._cv.notify_all()
        self._thread.join(timeout=2)

    # Voices

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

    # Live requests

    def render_sync(self, text: str, voice: str) -> Path:
        """Return the cached WAV for this sentence, synthesizing it if needed. Blocking."""
        engine = self.manager.engine
        if engine is None:
            raise EngineNotReady(self.manager.status.state)
        voice = self.resolve_voice(voice)
        key = AudioCache.key(engine.cache_tag, voice, text)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        with self._cv:
            future = self._inflight.get(key)
            if future is None:
                future = Future()
                self._inflight[key] = future
                self._live.append(_Job(key, text, voice, future))
                self._cv.notify()
        return future.result()

    async def render(self, text: str, voice: str) -> Path:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.render_sync, text, voice)

    # Background warming

    def warm(self, document_id: str, chunks: list[str], voice: str | None, position: int) -> int:
        """Keep the sentences after `position` cached. Returns how many are in the window."""
        engine = self.manager.engine
        if engine is None:
            raise EngineNotReady(self.manager.status.state)
        voice = self.resolve_voice(voice)
        position = max(0, min(position, max(len(chunks) - 1, 0)))
        with self._cv:
            plan = self._plan
            if plan is not None and plan.document_id == document_id and plan.voice == voice:
                plan.cursor = position
                plan.next_index = position
            else:
                self._plan = WarmPlan(
                    document_id, voice, list(chunks), position, position, self.config.warm_ahead
                )
            window = self._plan.end - position
            self._cv.notify()
        return max(0, window)

    def warm_status(self) -> dict[str, object]:
        with self._cv:
            plan = self._plan
            if plan is None:
                return {"active": False}
            return {
                "active": plan.has_work(),
                "document_id": plan.document_id,
                "voice": plan.voice,
                "cursor": plan.cursor,
                "next_index": plan.next_index,
                "end": plan.end,
            }

    def _next_warm_job_locked(self) -> _Job | None:
        """Advance the plan to the next sentence that still needs synthesis. Lock held."""
        plan = self._plan
        engine = self.manager.engine
        if plan is None or engine is None:
            return None
        while plan.has_work():
            index = plan.next_index
            plan.next_index += 1
            text = plan.chunks[index]
            key = AudioCache.key(engine.cache_tag, plan.voice, text)
            if key in self._inflight or self.cache.get(key) is not None:
                continue
            future: Future = Future()
            self._inflight[key] = future
            return _Job(key, text, plan.voice, future, background=True)
        return None

    # The worker

    def _worker(self) -> None:
        while not self._stop.is_set():
            job: _Job | None = None
            with self._cv:
                while (
                    not self._stop.is_set()
                    and not self._live
                    and not (self._plan is not None and self._plan.has_work())
                ):
                    self._cv.wait()
                if self._stop.is_set():
                    return
                if self._live:
                    job = self._live.popleft()
                else:
                    job = self._next_warm_job_locked()
            if job is not None:
                self._run(job)

    def _run(self, job: _Job) -> None:
        try:
            engine = self.manager.engine
            if engine is None:
                raise EngineNotReady(self.manager.status.state)
            samples = engine.synthesize(job.text, job.voice)
            data = encode_wav(samples, engine.sample_rate)
            path = self.cache.put(job.key, data)
        except Exception as error:
            with self._cv:
                self._inflight.pop(job.key, None)
            if job.background:
                log.debug("Warm synthesis failed: %s", error)
            job.future.set_exception(error)
            return
        with self._cv:
            self._inflight.pop(job.key, None)
        job.future.set_result(path)
