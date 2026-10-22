"""Gets the voice model onto disk and into memory without ever stranding the reader.

States: missing -> downloading -> loading -> ready, or error at any point. A failed
download leaves the browser's own voice reading, with a Retry in the UI; starting the
download again resumes any partial file instead of beginning over.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from ..config import Config
from .base import Engine
from .kokoro_engine import KokoroEngine
from .stub_engine import StubEngine

log = logging.getLogger("aloud.tts")


@dataclass
class ModelStatus:
    state: str = "missing"  # missing | downloading | loading | ready | error
    engine: str = "kokoro"
    progress: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    current_file: str = ""
    error: str | None = None
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "engine": self.engine,
            "progress": round(self.progress, 4),
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "current_file": self.current_file,
            "error": self.error,
            "updated_at": self.updated_at,
        }


class ModelManager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.status = ModelStatus(engine=config.tts_engine)
        self._engine: Engine | None = None
        if config.tts_engine == "stub":
            self._engine = StubEngine()
            self.status = ModelStatus(state="ready", engine="stub", progress=1.0)
        elif config.tts_engine != "kokoro":
            self.status = ModelStatus(
                state="error", engine=config.tts_engine, error="Unknown ALOUD_TTS_ENGINE"
            )

    @property
    def engine(self) -> Engine | None:
        return self._engine if self.status.state == "ready" else None

    @property
    def ready(self) -> bool:
        return self.status.state == "ready" and self._engine is not None

    def files_present(self) -> bool:
        return self.config.model_path.exists() and self.config.voices_path.exists()

    def start(self) -> ModelStatus:
        """Download if needed and load the engine, in a background thread. Idempotent."""
        if self.config.tts_engine != "kokoro":
            return self.status
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status
            if self.status.state == "ready":
                return self.status
            self.status = ModelStatus(state="downloading", engine="kokoro", progress=0.0)
            if self.files_present():
                self.status.state = "loading"
            self._thread = threading.Thread(target=self._run, name="aloud-model", daemon=True)
            self._thread.start()
        return self.status

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _set(self, **changes: Any) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(self.status, key, value)
            self.status.updated_at = time.time()

    def _run(self) -> None:
        try:
            self.config.models_dir.mkdir(parents=True, exist_ok=True)
            files = [
                (self.config.voices_url, self.config.voices_path),
                (self.config.model_url, self.config.model_path),
            ]
            for url, path in files:
                if not path.exists():
                    self._set(state="downloading", current_file=path.name, error=None)
                    download_file(url, path, self._report_progress)
            self._set(state="loading", progress=1.0, current_file="")
            engine = KokoroEngine(
                self.config.model_path, self.config.voices_path, threads=self.config.threads
            )
            engine.load()
            self._engine = engine
            self._set(state="ready", error=None)
        except Exception as error:  # a failure here must never take the app down
            log.warning("Voice model unavailable: %s", error)
            self._set(state="error", error=str(error)[:500])

    def _report_progress(self, downloaded: int, total: int) -> None:
        progress = downloaded / total if total else 0.0
        self._set(downloaded_bytes=downloaded, total_bytes=total, progress=progress)


def download_file(url: str, destination: Path, on_progress=None, chunk_size: int = 1 << 20) -> None:
    """Stream `url` to `destination`, resuming a partial download when the server allows."""
    partial = destination.with_suffix(destination.suffix + ".part")
    existing = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "aloud-reader/0.1"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    timeout = httpx.Timeout(30.0, read=120.0)
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        with client.stream("GET", url, headers=headers) as response:
            if response.status_code == 416:
                # The partial file is already complete.
                partial.replace(destination)
                return
            if response.status_code == 200 and existing:
                existing = 0  # the server ignored the range; start over
            if response.status_code not in (200, 206):
                raise RuntimeError(f"Download failed with HTTP {response.status_code} for {url}")
            length = response.headers.get("Content-Length")
            total = existing + int(length) if length else 0
            mode = "ab" if existing else "wb"
            downloaded = existing
            with open(partial, mode) as handle:
                for chunk in response.iter_bytes(chunk_size):
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if on_progress:
                        on_progress(downloaded, total)
    if total and downloaded < total:
        raise RuntimeError(f"Download of {destination.name} ended early ({downloaded}/{total})")
    partial.replace(destination)
