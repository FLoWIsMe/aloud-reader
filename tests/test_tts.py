from __future__ import annotations

import io
import threading
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import numpy as np

from server.config import Config
from server.tts.base import encode_wav, wav_duration_seconds
from server.tts.cache import AudioCache
from server.tts.kokoro_engine import describe_voice, sort_voices, voice_language
from server.tts.manager import ModelManager, download_file
from server.tts.stub_engine import StubEngine


def test_encode_wav_roundtrip() -> None:
    samples = np.linspace(-1, 1, 2400, dtype=np.float32)
    data = encode_wav(samples, 24000)
    with wave.open(io.BytesIO(data), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 24000
        assert handle.getnframes() == 2400
    assert abs(wav_duration_seconds(data) - 0.1) < 1e-6


def test_stub_engine_scales_with_text() -> None:
    engine = StubEngine()
    short = engine.synthesize("Hi.", "stub_low")
    long = engine.synthesize("This sentence has quite a few more words in it than hi.", "stub_low")
    assert len(long) > len(short)
    assert float(np.abs(short).max()) <= 0.2001


def test_kokoro_voice_metadata() -> None:
    voice = describe_voice("bf_emma")
    assert (voice.language, voice.language_name, voice.gender, voice.name) == (
        "en-gb",
        "English (UK)",
        "female",
        "Emma",
    )
    assert voice_language("zm_yunjian") == "cmn"
    assert voice_language("??") == "en-us"
    ordered = sort_voices(["zf_xiaobei", "am_michael", "af_heart", "af_alloy"])
    assert ordered[:2] == ["af_heart", "am_michael"]
    assert ordered[2:] == ["af_alloy", "zf_xiaobei"]


def test_cache_put_get_and_eviction(tmp_path: Path) -> None:
    cache = AudioCache(tmp_path / "cache", max_bytes=3000)
    keys = [AudioCache.key("stub", "v", f"text {i}") for i in range(5)]
    for key in keys:
        cache.put(key, b"x" * 1000)
    assert cache.stats()["bytes"] <= 3000
    present = [key for key in keys if cache.get(key) is not None]
    assert 1 <= len(present) <= 3
    assert cache.get(keys[-1]) is not None  # the newest file survives
    assert cache.clear() == len(present)
    assert cache.stats()["bytes"] == 0


class _RangeHandler(BaseHTTPRequestHandler):
    payload = b"0123456789" * 1000
    fail_first_half = False
    served = 0

    def log_message(self, *_args) -> None:  # keep test output quiet
        return

    def do_GET(self) -> None:
        start = 0
        if "Range" in self.headers:
            start = int(self.headers["Range"].split("=")[1].rstrip("-"))
        body = self.payload[start:]
        if type(self).fail_first_half and type(self).served == 0:
            body = body[: len(body) // 2]  # cut the connection early once
            type(self).served += 1
        self.send_response(206 if start else 200)
        self.send_header("Content-Length", str(len(self.payload) - start))
        self.end_headers()
        self.wfile.write(body)


def _serve(handler) -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/file.bin"


def test_download_resumes_a_partial_file(tmp_path: Path) -> None:
    _RangeHandler.fail_first_half = True
    _RangeHandler.served = 0
    server, url = _serve(_RangeHandler)
    try:
        destination = tmp_path / "file.bin"
        progress: list[tuple[int, int]] = []
        try:
            download_file(url, destination, lambda d, t: progress.append((d, t)))
        except Exception:
            pass  # first attempt was cut short on purpose
        assert not destination.exists()
        assert destination.with_suffix(".bin.part").exists()
        download_file(url, destination, lambda d, t: progress.append((d, t)))
        assert destination.read_bytes() == _RangeHandler.payload
        assert progress[-1] == (len(_RangeHandler.payload), len(_RangeHandler.payload))
    finally:
        server.shutdown()


def test_manager_reports_download_errors_without_crashing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALOUD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ALOUD_TTS_ENGINE", "kokoro")
    monkeypatch.setenv("ALOUD_KOKORO_MODEL_URL", "http://127.0.0.1:9/missing.onnx")
    monkeypatch.setenv("ALOUD_KOKORO_VOICES_URL", "http://127.0.0.1:9/missing.bin")
    config = Config.from_env()
    config.ensure_dirs()
    manager = ModelManager(config)
    assert manager.status.state == "missing"
    manager.start()
    manager.wait(timeout=30)
    assert manager.status.state == "error"
    assert manager.status.error
    assert manager.engine is None
    # Retrying is allowed and goes through the same path again.
    manager.start()
    manager.wait(timeout=30)
    assert manager.status.state == "error"


def test_stub_manager_is_ready_immediately(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALOUD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ALOUD_TTS_ENGINE", "stub")
    manager = ModelManager(Config.from_env())
    assert manager.ready
    assert manager.engine is not None
    assert manager.start().state == "ready"
