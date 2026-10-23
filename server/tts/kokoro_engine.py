"""Kokoro-82M through onnxruntime on the CPU: natural voices with no cloud and no GPU."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np

from .base import Voice, trim_silence, with_pause

log = logging.getLogger("aloud.tts")

SAMPLE_RATE = 24000

# The first letter of a Kokoro voice id is its language, the second its gender.
LANGUAGES = {
    "a": ("en-us", "English (US)"),
    "b": ("en-gb", "English (UK)"),
    "e": ("es", "Spanish"),
    "f": ("fr-fr", "French"),
    "h": ("hi", "Hindi"),
    "i": ("it", "Italian"),
    "j": ("ja", "Japanese"),
    "p": ("pt-br", "Portuguese (Brazil)"),
    "z": ("cmn", "Chinese (Mandarin)"),
}

# Voices the Kokoro authors grade highest come first in the picker.
FEATURED = ["af_heart", "af_bella", "am_michael", "bf_emma", "am_fenrir", "af_nicole", "bm_george"]
GRADES = {
    "af_heart": "best",
    "af_bella": "best",
    "af_nicole": "good",
    "am_michael": "good",
    "am_fenrir": "good",
    "am_puck": "good",
    "bf_emma": "good",
    "bm_george": "good",
    "bm_fable": "good",
    "ff_siwis": "good",
    "jf_alpha": "good",
    "zf_xiaobei": "good",
}

DEFAULT_VOICE = "af_heart"
DEFAULT_PAUSE_MS = 120
TRIM_TOP_DB = 40.0
PREVIEW_TEXT = {
    "en-us": "Natural voices, right on your computer. This is how I sound.",
    "en-gb": "Natural voices, right on your computer. This is how I sound.",
    "es": "Voces naturales, directamente en tu ordenador. Así es como sueno.",
    "fr-fr": "Des voix naturelles, directement sur votre ordinateur. Voici ma voix.",
    "hi": "प्राकृतिक आवाज़ें, सीधे आपके कंप्यूटर पर।",
    "it": "Voci naturali, direttamente sul tuo computer. Ecco come suono.",
    "ja": "自然な声を、あなたのパソコンで。これが私の声です。",
    "pt-br": "Vozes naturais, direto no seu computador. É assim que eu sou.",
    "cmn": "自然的声音，就在你的电脑上。这就是我的声音。",
}


def voice_language(voice_id: str) -> str:
    return LANGUAGES.get(voice_id[:1], LANGUAGES["a"])[0]


def describe_voice(voice_id: str) -> Voice:
    language, language_name = LANGUAGES.get(voice_id[:1], LANGUAGES["a"])
    gender = {"f": "female", "m": "male"}.get(voice_id[1:2], "neutral")
    raw_name = voice_id.split("_", 1)[1] if "_" in voice_id else voice_id
    name = raw_name.replace("_", " ").title()
    return Voice(
        id=voice_id,
        name=name,
        engine="kokoro",
        language=language,
        language_name=language_name,
        gender=gender,
        quality=GRADES.get(voice_id, "standard"),
    )


def sort_voices(voice_ids: list[str]) -> list[str]:
    featured = [voice for voice in FEATURED if voice in voice_ids]
    rest = sorted(voice for voice in voice_ids if voice not in featured)
    return featured + rest


class KokoroEngine:
    """Loads lazily; `load()` is slow (a few seconds) and runs off the event loop."""

    name = "kokoro"
    sample_rate = SAMPLE_RATE

    def __init__(
        self,
        model_path: Path,
        voices_path: Path,
        threads: int = 0,
        pause_ms: int = DEFAULT_PAUSE_MS,
    ) -> None:
        self.model_path = Path(model_path)
        self.voices_path = Path(voices_path)
        self.threads = threads
        self.pause_ms = max(0, pause_ms)
        self._kokoro = None
        self._voice_ids: list[str] = []
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._kokoro is not None

    @property
    def cache_tag(self) -> str:
        return f"{self.name}:trim{int(TRIM_TOP_DB)}:pause{self.pause_ms}"

    def load(self) -> None:
        with self._lock:
            if self._kokoro is not None:
                return
            import onnxruntime as ort
            from kokoro_onnx import Kokoro

            # kokoro-onnx logs a harmless "words count mismatch" line for some sentences.
            logging.getLogger("phonemizer").setLevel(logging.ERROR)

            options = ort.SessionOptions()
            if self.threads > 0:
                options.intra_op_num_threads = self.threads
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            session = ort.InferenceSession(
                str(self.model_path), sess_options=options, providers=["CPUExecutionProvider"]
            )
            kokoro = Kokoro.from_session(session, str(self.voices_path))
            self._voice_ids = sort_voices(list(kokoro.get_voices()))
            self._kokoro = kokoro
            log.info("Kokoro loaded with %d voices", len(self._voice_ids))

    def voices(self) -> list[Voice]:
        return [describe_voice(voice_id) for voice_id in self._voice_ids]

    def has_voice(self, voice_id: str) -> bool:
        return voice_id in self._voice_ids

    def synthesize(self, text: str, voice: str) -> np.ndarray:
        if self._kokoro is None:
            raise RuntimeError("Kokoro is not loaded")
        if voice not in self._voice_ids:
            voice = DEFAULT_VOICE if DEFAULT_VOICE in self._voice_ids else self._voice_ids[0]
        samples, _rate = self._kokoro.create(
            text, voice=voice, speed=1.0, lang=voice_language(voice), trim=True
        )
        # kokoro-onnx only drops what is 60 dB below peak, which leaves 100 to 200 ms of
        # near-silence on every sentence. Cut tighter, then add one deliberate pause so the
        # gap between sentences is a setting rather than an accident.
        trimmed = trim_silence(samples, self.sample_rate, top_db=TRIM_TOP_DB)
        return with_pause(trimmed, self.sample_rate, self.pause_ms)
