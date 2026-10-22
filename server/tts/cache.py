"""A size-capped on-disk cache of synthesized sentences, keyed by engine, voice and text."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path


class AudioCache:
    def __init__(self, directory: Path, max_bytes: int) -> None:
        self.directory = Path(directory)
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._total = self._scan()

    @staticmethod
    def key(engine: str, voice: str, text: str) -> str:
        digest = hashlib.sha256(f"{engine}\x1f{voice}\x1f{text}".encode()).hexdigest()
        return digest

    def path_for(self, key: str) -> Path:
        return self.directory / key[:2] / f"{key}.wav"

    def get(self, key: str) -> Path | None:
        path = self.path_for(key)
        if path.exists():
            try:
                now = time.time()
                os.utime(path, (now, now))
            except OSError:
                pass
            return path
        return None

    def put(self, key: str, data: bytes) -> Path:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        with open(temp, "wb") as handle:
            handle.write(data)
        temp.replace(path)
        with self._lock:
            self._total += len(data)
            if self._total > self.max_bytes:
                self._evict_locked()
        return path

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"bytes": self._total, "max_bytes": self.max_bytes}

    def clear(self) -> int:
        removed = 0
        with self._lock:
            for path in self.directory.rglob("*.wav"):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
            self._total = self._scan()
        return removed

    def _scan(self) -> int:
        return sum(path.stat().st_size for path in self.directory.rglob("*.wav"))

    def _evict_locked(self) -> None:
        """Drop the least recently used files until the cache is under 90% of its cap."""
        target = int(self.max_bytes * 0.9)
        entries = []
        for path in self.directory.rglob("*.wav"):
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
        entries.sort()
        total = sum(size for _, size, _ in entries)
        for _, size, path in entries:
            if total <= target:
                break
            try:
                path.unlink()
                total -= size
            except OSError:
                pass
        self._total = total
