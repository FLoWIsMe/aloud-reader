"""Runtime configuration, read once from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Aloud"
APP_VERSION = "0.1.0"

KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
DEFAULT_MODEL_URL = f"{KOKORO_RELEASE}/kokoro-v1.0.onnx"
DEFAULT_VOICES_URL = f"{KOKORO_RELEASE}/voices-v1.0.bin"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    data_dir: Path
    host: str
    port: int
    tts_engine: str
    auto_download: bool
    model_url: str
    voices_url: str
    cache_max_bytes: int
    threads: int
    sentence_pause_ms: int
    warm_ahead: int
    max_upload_bytes: int
    url_fetch_timeout: float
    log_level: str

    @classmethod
    def from_env(cls) -> Config:
        data_dir = Path(os.environ.get("ALOUD_DATA_DIR", "./data")).expanduser().resolve()
        return cls(
            data_dir=data_dir,
            host=os.environ.get("ALOUD_HOST", "0.0.0.0"),
            port=_env_int("ALOUD_PORT", 8787),
            tts_engine=os.environ.get("ALOUD_TTS_ENGINE", "kokoro").strip().lower(),
            auto_download=_env_bool("ALOUD_AUTO_DOWNLOAD", True),
            model_url=os.environ.get("ALOUD_KOKORO_MODEL_URL", DEFAULT_MODEL_URL),
            voices_url=os.environ.get("ALOUD_KOKORO_VOICES_URL", DEFAULT_VOICES_URL),
            cache_max_bytes=_env_int("ALOUD_CACHE_MAX_MB", 2048) * 1024 * 1024,
            threads=_env_int("ALOUD_THREADS", 0),
            sentence_pause_ms=_env_int("ALOUD_SENTENCE_PAUSE_MS", 120),
            warm_ahead=_env_int("ALOUD_WARM_AHEAD", 80),
            max_upload_bytes=_env_int("ALOUD_MAX_UPLOAD_MB", 50) * 1024 * 1024,
            url_fetch_timeout=float(_env_int("ALOUD_URL_TIMEOUT", 30)),
            log_level=os.environ.get("ALOUD_LOG_LEVEL", "info").lower(),
        )

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "aloud.sqlite3"

    @property
    def model_path(self) -> Path:
        return self.models_dir / "kokoro-v1.0.onnx"

    @property
    def voices_path(self) -> Path:
        return self.models_dir / "voices-v1.0.bin"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.models_dir, self.cache_dir):
            path.mkdir(parents=True, exist_ok=True)
