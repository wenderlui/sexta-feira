"""Ouvir: transcrição local com faster-whisper (opcional, roda na GPU do PC)."""

from __future__ import annotations

import asyncio
import io
import gc
import threading
import time
from typing import Any

from .config import Settings


def _add_cuda_dll_dirs() -> None:
    """No Windows, as DLLs do CUDA instaladas via pip (nvidia-cublas/cudnn) não ficam no PATH."""
    import os
    import sys

    if sys.platform != "win32":
        return
    try:
        import nvidia  # pacote namespace dos wheels nvidia-*-cu12
    except ImportError:
        return
    for base in getattr(nvidia, "__path__", []):
        for sub in ("cublas", "cudnn", "cuda_runtime"):
            d = os.path.join(base, sub, "bin")
            if os.path.isdir(d):
                os.add_dll_directory(d)
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


class Transcriber:
    def __init__(self, settings: Settings):
        self.s = settings
        self._model = None
        self._lock = threading.Lock()
        self.error: str | None = None
        self.last_used = 0.0

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def unload_if_idle(self, idle_seconds: float) -> bool:
        """Tira o Whisper da placa de vídeo se ninguém falou nos últimos minutos."""
        with self._lock:
            if self._model is None or time.time() - self.last_used < idle_seconds:
                return False
            self._model = None
        gc.collect()
        return True

    @property
    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            self.error = "faster-whisper não instalado (pip install -r requirements-voz.txt)"
            return False
        return True

    def _load(self):
        self.last_used = time.time()
        with self._lock:
            if self._model is None:
                _add_cuda_dll_dirs()
                from faster_whisper import WhisperModel

                try:
                    self._model = WhisperModel(
                        self.s.whisper_model, device="cuda", compute_type="int8_float16"  # metade da VRAM
                    )
                except Exception:
                    # Sem CUDA disponível: CPU funciona, só que mais devagar.
                    self._model = WhisperModel(
                        self.s.whisper_model, device="cpu", compute_type="int8"
                    )
            return self._model

    def _run(self, model, audio: bytes) -> dict[str, Any]:
        segments, info = model.transcribe(
            io.BytesIO(audio), language="pt", vad_filter=True, beam_size=1,
            # Ajuda o Whisper a escrever a palavra de ativação do jeito certo.
            initial_prompt="Sexta-feira, ",
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return {"text": text, "duration": round(info.duration, 2)}

    def _transcribe(self, audio: bytes) -> dict[str, Any]:
        model = self._load()
        try:
            return self._run(model, audio)
        except RuntimeError as exc:
            # No Windows, faltar a DLL do CUDA (cublas/cudnn) só aparece aqui.
            if not any(k in str(exc).lower() for k in ("cuda", "cublas", "cudnn", ".dll")):
                raise
            from faster_whisper import WhisperModel

            with self._lock:
                self._model = WhisperModel(self.s.whisper_model, device="cpu", compute_type="int8")
            return self._run(self._model, audio)

    async def transcribe(self, audio: bytes) -> dict[str, Any]:
        return await asyncio.to_thread(self._transcribe, audio)

    async def warm_up(self) -> None:
        if self.available:
            await asyncio.to_thread(self._load)
