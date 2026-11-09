"""Falar: voz gerada no PC com Kokoro (local, gratuito), tocada pelo iPad.

No iPad, com o microfone ligado, a voz do Safari (speechSynthesis) sai muda.
Gerar o áudio aqui e tocá-lo pelo mesmo AudioContext do microfone resolve isso.
"""

from __future__ import annotations

import asyncio
import io
import threading
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


def _download(url: str, path: Path) -> None:
    # httpx usa os certificados do certifi; o urllib no Windows falha com CERTIFICATE_VERIFY_FAILED.
    import httpx

    tmp = path.with_suffix(path.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    tmp.replace(path)


class Kokoro:
    """Voz local (CPU ou GPU), funciona sem internet."""

    def __init__(self, settings: Settings, models_dir: Path = MODELS_DIR):
        self.s = settings
        self.dir = models_dir
        self._engine = None
        self._lock = threading.Lock()

    @staticmethod
    def installed() -> bool:
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return False
        return True

    def _load(self):
        with self._lock:
            if self._engine is None:
                from kokoro_onnx import Kokoro as Engine

                self.dir.mkdir(parents=True, exist_ok=True)
                for name in FILES:  # baixa uma vez só (~330 MB)
                    path = self.dir / name
                    if not path.exists():
                        _download(BASE_URL + name, path)
                self._engine = Engine(str(self.dir / FILES[0]), str(self.dir / FILES[1]))
            return self._engine

    def _speak(self, text: str) -> bytes:
        samples, rate = self._load().create(
            text, voice=self.s.tts_voice, speed=self.s.tts_speed, lang="pt-br"
        )
        return to_wav(samples, rate)

    async def speak(self, text: str) -> tuple[bytes, str]:
        return await asyncio.to_thread(self._speak, text), "audio/wav"


class Edge:
    """Voz neural da Microsoft (edge-tts): bem natural e rápida, gratuita, precisa de internet."""

    def __init__(self, settings: Settings):
        self.s = settings

    @staticmethod
    def installed() -> bool:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False
        return True

    async def speak(self, text: str) -> tuple[bytes, str]:
        import edge_tts

        pct = round((self.s.tts_speed - 1) * 100)
        com = edge_tts.Communicate(text, self.s.edge_voice, rate=f"{pct:+d}%")
        audio = bytearray()
        async for chunk in com.stream():
            if chunk.get("type") == "audio":
                audio += chunk["data"]
        if not audio:
            raise RuntimeError("edge-tts não devolveu áudio")
        return bytes(audio), "audio/mpeg"


class Speaker:
    """Escolhe a voz: a da Microsoft se configurada (com a local como reserva) ou a local."""

    def __init__(self, settings: Settings, models_dir: Path = MODELS_DIR):
        self.s = settings
        self.kokoro = Kokoro(settings, models_dir)
        self.edge = Edge(settings)
        self.error: str | None = None
        self.last_engine: str | None = None

    def _engines(self) -> list:
        order = [self.edge, self.kokoro] if self.s.tts_engine == "edge" else [self.kokoro]
        return [e for e in order if e.installed()]

    @property
    def available(self) -> bool:
        if self._engines():
            return True
        self.error = "nenhuma voz instalada (pip install -r requirements-voz.txt)"
        return False

    async def speak(self, text: str) -> tuple[bytes, str]:
        errors = []
        for engine in self._engines():
            try:
                result = await engine.speak(text)
                self.last_engine = type(engine).__name__.lower()
                return result
            except Exception as exc:  # sem internet etc.: tenta a próxima
                errors.append(f"{type(engine).__name__}: {exc}")
        raise RuntimeError("; ".join(errors) or "nenhuma voz instalada")

    async def warm_up(self) -> None:
        if self.available:
            await self.speak("Oi.")
