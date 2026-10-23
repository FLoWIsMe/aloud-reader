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


def test_trim_silence_keeps_speech_and_margins() -> None:
    from server.tts.base import trim_silence, with_pause

    rate = 16000
    tone = 0.5 * np.sin(2 * np.pi * 440 * np.arange(rate // 2) / rate).astype(np.float32)
    quiet = np.full(rate // 2, 0.0005, dtype=np.float32)  # 500 ms of near-silence each side
    samples = np.concatenate([quiet, tone, quiet])
    trimmed = trim_silence(samples, rate, top_db=40, head_ms=20, tail_ms=30)
    # 500 ms tone plus the 20 ms and 30 ms margins, give or take one 10 ms frame.
    assert abs(len(trimmed) - (rate // 2 + 50 * rate // 1000)) <= rate // 100
    assert float(np.abs(trimmed).max()) > 0.4
    padded = with_pause(trimmed, rate, 150)
    assert len(padded) == len(trimmed) + 150 * rate // 1000
    assert float(np.abs(padded[-100:]).max()) == 0.0
    assert with_pause(trimmed, rate, 0) is trimmed


def test_trim_silence_leaves_silence_alone() -> None:
    from server.tts.base import trim_silence

    silent = np.zeros(4000, dtype=np.float32)
    assert len(trim_silence(silent, 16000)) == 4000
    assert len(trim_silence(np.zeros(5, dtype=np.float32), 16000)) == 5


def _service(tmp_path: Path, monkeypatch, delay: float = 0.0):
    import time

    from server.tts.cache import AudioCache
    from server.tts.service import SynthService

    monkeypatch.setenv("ALOUD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ALOUD_TTS_ENGINE", "stub")
    monkeypatch.setenv("ALOUD_WARM_AHEAD", "6")
    config = Config.from_env()
    config.ensure_dirs()
    manager = ModelManager(config)
    engine = manager.engine
    assert engine is not None
    if delay:
        original = engine.synthesize

        def slow(text: str, voice: str) -> np.ndarray:
            time.sleep(delay)
            return original(text, voice)

        monkeypatch.setattr(engine, "synthesize", slow)
    cache = AudioCache(config.cache_dir, 50 * 1024 * 1024)
    return SynthService(config, manager, cache), cache, engine


def _wait_until(check, timeout: float = 10.0) -> bool:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return check()


def test_warm_fills_the_window_after_the_position(tmp_path: Path, monkeypatch) -> None:
    from server.tts.cache import AudioCache

    service, cache, engine = _service(tmp_path, monkeypatch)
    try:
        chunks = [f"Sentence number {i}." for i in range(20)]
        window = service.warm("doc", chunks, "stub_low", position=5)
        assert window == 6

        def keys(indices):
            return [AudioCache.key(engine.cache_tag, "stub_low", chunks[i]) for i in indices]

        assert _wait_until(lambda: all(cache.get(k) for k in keys(range(5, 11))))
        assert _wait_until(lambda: not service.warm_status()["active"])
        assert not any(cache.get(k) for k in keys(range(0, 5)))
        assert not any(cache.get(k) for k in keys(range(11, 20)))
        # Moving the listener forward extends the window from the new position.
        service.warm("doc", chunks, "stub_low", position=12)
        assert _wait_until(lambda: all(cache.get(k) for k in keys(range(12, 18))))
    finally:
        service.close()


def test_live_requests_jump_ahead_of_warming(tmp_path: Path, monkeypatch) -> None:
    import time

    service, cache, engine = _service(tmp_path, monkeypatch, delay=0.05)
    try:
        chunks = [f"Background sentence {i}." for i in range(40)]
        service.warm("doc", chunks, "stub_low", position=0)
        time.sleep(0.08)  # let one warm job start
        started = time.time()
        path = service.render_sync("Somebody is waiting for this one.", "stub_low")
        elapsed = time.time() - started
        assert path.exists()
        # One warm job may be mid-flight (50 ms) plus our own synthesis (50 ms); the queued
        # warm window (6 more jobs) must not run first.
        assert elapsed < 0.25, f"live request waited {elapsed:.2f}s behind warming"
    finally:
        service.close()


def test_render_dedupes_concurrent_requests(tmp_path: Path, monkeypatch) -> None:
    import threading

    service, cache, engine = _service(tmp_path, monkeypatch, delay=0.05)
    calls: list[str] = []
    original = engine.synthesize

    def counting(text: str, voice: str) -> np.ndarray:
        calls.append(text)
        return original(text, voice)

    monkeypatch.setattr(engine, "synthesize", counting)
    try:
        results: list[Path] = []
        threads = [
            threading.Thread(
                target=lambda: results.append(service.render_sync("Same sentence.", "stub_low"))
            )
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        assert len(results) == 4
        assert len({str(path) for path in results}) == 1
        assert calls.count("Same sentence.") == 1
    finally:
        service.close()


def test_synthesis_errors_reach_the_caller(tmp_path: Path, monkeypatch) -> None:
    service, cache, engine = _service(tmp_path, monkeypatch)

    def broken(text: str, voice: str) -> np.ndarray:
        raise RuntimeError("boom")

    monkeypatch.setattr(engine, "synthesize", broken)
    try:
        import pytest

        with pytest.raises(RuntimeError, match="boom"):
            service.render_sync("Will fail.", "stub_low")
        # A failed key is not stuck in flight: the next attempt runs again.
        with pytest.raises(RuntimeError, match="boom"):
            service.render_sync("Will fail.", "stub_low")
    finally:
        service.close()
