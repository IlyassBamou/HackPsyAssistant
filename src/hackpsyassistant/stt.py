"""Speech-to-text: browser records 16 kHz mono PCM16 WAV, Whisper transcribes it in French.

The model is lazy-loaded on first use (or via warmup()) and cached for the process lifetime.
No ffmpeg needed: the WAV is parsed with the stdlib `wave` module.
"""
from __future__ import annotations

import io
import os
import threading
import wave

import numpy as np

_pipe = None
_lock = threading.Lock()

MODEL = os.environ.get("HACKPSY_STT", "openai/whisper-small")


def _load():
    global _pipe
    with _lock:
        if _pipe is None:
            from transformers import pipeline
            _pipe = pipeline("automatic-speech-recognition", model=MODEL)
    return _pipe


def warmup() -> str:
    _load()
    return MODEL


def transcribe(wav_bytes: bytes) -> str:
    pipe = _load()
    with wave.open(io.BytesIO(wav_bytes)) as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    if sr != 16000:  # resample linearly (browser should already send 16 kHz)
        n = int(len(audio) * 16000 / sr)
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
    if len(audio) < 1600:  # < 0.1 s
        return ""
    out = pipe({"array": audio, "sampling_rate": 16000},
               generate_kwargs={"language": "french", "task": "transcribe"})
    return out["text"].strip()
