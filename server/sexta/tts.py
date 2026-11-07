"""Falar: voz gerada no PC com Kokoro (local, gratuito), tocada pelo iPad.

No iPad, com o microfone ligado, a voz do Safari (speechSynthesis) sai muda.
Gerar o áudio aqui e tocá-lo pelo mesmo AudioContext do microfone resolve isso.
"""

from __future__ import annotations

import asyncio
import io
import threading
import urllib.request
import wave
from pathlib import Path

from .config import Settings

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
BASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")


def to_wav(samples, rate: int) -> bytes:
    """Converte amostras float (-1..1) em WAV 16 bits mono."""
    try:
        import numpy as np

        pcm = (np.clip(np.asarray(samples, dtype="float32"), -1, 1) * 32767).astype("<i2").tobytes()
    except ImportError:  # sem numpy (só nos testes): mais lento, mesmo resultado
        import array
        import sys

        a = array.array("h", (int(max(-1.0, min(1.0, x)) * 32767) for x in samples))
        if sys.byteorder == "big":
            a.byteswap()
        pcm = a.tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class Speaker:
    def __init__(self, settings: Settings, models_dir: Path = MODELS_DIR):
        self.s = settings
        self.dir = models_dir
        self._engine = None
        self._lock = threading.Lock()
        self.error: str | None = None

    @property
    def available(self) -> bool:
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            self.error = "kokoro-onnx não instalado (pip install -r requirements-voz.txt)"
            return False
        return True

    def _load(self):
        with self._lock:
            if self._engine is None:
                from kokoro_onnx import Kokoro

                self.dir.mkdir(parents=True, exist_ok=True)
                for name in FILES:  # baixa uma vez só (~330 MB)
                    path = self.dir / name
                    if not path.exists():
                        tmp = path.with_suffix(path.suffix + ".part")
                        urllib.request.urlretrieve(BASE_URL + name, tmp)
                        tmp.replace(path)
                self._engine = Kokoro(str(self.dir / FILES[0]), str(self.dir / FILES[1]))
            return self._engine

    def _speak(self, text: str) -> bytes:
        engine = self._load()
        samples, rate = engine.create(
            text, voice=self.s.tts_voice, speed=self.s.tts_speed, lang="pt-br"
        )
        return to_wav(samples, rate)

    async def speak(self, text: str) -> bytes:
        return await asyncio.to_thread(self._speak, text)

    async def warm_up(self) -> None:
        if self.available:
            await asyncio.to_thread(self._speak, "Oi.")
