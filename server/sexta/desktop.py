"""API do programa do PC (janela da Sexta-feira): serviços, modelos, registros e modo offline.

Tudo aqui roda no próprio PC. Nada vai para a internet, exceto o teste de conexão
(um pedido rápido, sem dados pessoais) quando o modo offline está desligado.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from collections import deque
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import system

MODEL_NAME = re.compile(r"^[A-Za-z0-9_.:/\-]{1,120}$")

# Modelos abertos sugeridos para o PC (RTX 4070 Ti, 12 GB). Só aparecem como dica;
# baixar é com "ollama pull <nome>" no terminal (ou pelo botão, na etapa 2).
SUGGESTED_MODELS = [
    {"name": "qwen3:8b", "size_gb": 5.2, "note": "Padrão: rápido, bom em português e usa ferramentas."},
    {"name": "dolphin3:8b", "size_gb": 4.9,
     "note": "Menos restrito (ajustado para obedecer o dono). Bom para uso pessoal."},
    {"name": "qwen3:14b", "size_gb": 9.3, "note": "Mais inteligente, mais lento; cabe nos 12 GB."},
    {"name": "gemma3:12b", "size_gb": 8.1, "note": "Bom texto em português, entende imagens."},
    {"name": "qwen2.5vl:7b", "size_gb": 6.0, "note": "Visão (câmera)."},
]


class ChatModelIn(BaseModel):
    name: str = Field(pattern=MODEL_NAME.pattern)


def tail(path: Path, lines: int = 200, contains: str | None = None) -> list[str]:
    """Últimas linhas de um arquivo de texto, sem ler o arquivo inteiro na memória."""
    if not path.is_file():
        return []
    needle = (contains or "").lower()
    out: deque[str] = deque(maxlen=max(1, min(lines, 2000)))
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not needle or needle in line.lower():
                out.append(line.rstrip("\n"))
    return list(out)


def _tailscale() -> dict[str, Any]:
    exe = shutil.which("tailscale")
    win = Path(r"C:\Program Files\Tailscale\tailscale.exe")
    if not exe and win.is_file():
        exe = str(win)
    if not exe:
        return {"ok": False, "detail": "não instalado"}
    try:
        out = subprocess.run([exe, "status", "--json"], capture_output=True, text=True,
                             timeout=5, check=False).stdout
        data = json.loads(out or "{}")
        state = data.get("BackendState", "?")
        name = (data.get("Self") or {}).get("DNSName", "").rstrip(".")
        return {"ok": state == "Running", "detail": f"{state} {name}".strip()}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"ok": False, "detail": "sem resposta"}


def register(app: FastAPI, settings, store, state: dict, ears, mouth, log_dir: Path) -> None:
    def client() -> httpx.AsyncClient:
        return state["client"]

    async def _ollama(path: str, method: str = "GET", **kw) -> dict:
        r = await client().request(method, f"{settings.ollama_url}{path}", timeout=kw.pop("timeout", 5), **kw)
        r.raise_for_status()
        return r.json() if r.content else {}

    async def _internet() -> dict[str, Any]:
        if settings.offline:
            return {"ok": None, "detail": "modo offline (não testado)"}
        try:
            r = await client().get("https://www.gstatic.com/generate_204", timeout=3)
            return {"ok": r.status_code in (200, 204), "detail": f"HTTP {r.status_code}"}
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": type(exc).__name__}

    async def _ha() -> dict[str, Any]:
        home = state.get("home")
        if home is None or not getattr(home, "configured", False):
            return {"ok": None, "detail": "não configurado"}
        c = store.connection("homeassistant")
        try:
            r = await client().get(f"{c.get('url', '').rstrip('/')}/api/",
                                   headers={"Authorization": f"Bearer {c.get('token', '')}"}, timeout=4)
            return {"ok": r.status_code == 200, "detail": f"HTTP {r.status_code}"}
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": type(exc).__name__}

    @app.get("/api/desktop/services")
    async def services():
        """Estado de cada peça da Sexta-feira, para a tela Serviços do programa."""
        ollama: dict[str, Any]
        try:
            tags = await _ollama("/api/tags")
            ps = await _ollama("/api/ps")
            loaded = [m.get("name") for m in ps.get("models", [])]
            ollama = {"ok": True, "detail": f"{len(tags.get('models', []))} modelos, "
                                            f"{len(loaded)} na placa de vídeo", "loaded": loaded}
        except (httpx.HTTPError, ValueError):
            ollama = {"ok": False, "detail": f"sem resposta em {settings.ollama_url}", "loaded": []}
        net, ha, ts, pc = await asyncio.gather(_internet(), _ha(), asyncio.to_thread(_tailscale),
                                               system.snapshot())
        voice_engine = "kokoro" if settings.offline or settings.tts_engine != "edge" else "edge"
        return {
            "offline": settings.offline,
            "chat_model": settings.chat_model,
            "vision_model": settings.vision_model,
            "pc": pc,
            "services": [
                {"id": "servidor", "name": "Servidor", "ok": True, "detail": "rodando"},
                {"id": "ollama", "name": "IA (Ollama)", **ollama},
                {"id": "whisper", "name": "Ouvir (Whisper)", "ok": bool(ears.available),
                 "detail": ("carregado" if getattr(ears, "loaded", False) else "em espera")
                 if ears.available else (ears.error or "indisponível")},
                {"id": "voz", "name": "Falar", "ok": bool(mouth.available),
                 "detail": voice_engine if mouth.available else (mouth.error or "indisponível")},
                {"id": "internet", "name": "Internet", **net},
                {"id": "homeassistant", "name": "Home Assistant", **ha},
                {"id": "tailscale", "name": "Tailscale (iPad)", **ts},
            ],
        }

    @app.get("/api/models")
    async def models():
        try:
            tags = await _ollama("/api/tags")
            ps = await _ollama("/api/ps")
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=f"Ollama não respondeu: {exc}")
        vram = {m.get("name"): m.get("size_vram", 0) for m in ps.get("models", [])}
        installed = []
        for m in tags.get("models", []):
            name = m.get("name", "")
            details = m.get("details") or {}
            installed.append({
                "name": name,
                "size_gb": round((m.get("size") or 0) / 1024**3, 1),
                "params": details.get("parameter_size"),
                "quant": details.get("quantization_level"),
                "loaded": name in vram,
                "vram_gb": round((vram.get(name) or 0) / 1024**3, 1),
                "role": "conversa" if name == settings.chat_model or name.startswith(settings.chat_model + ":")
                else "visão" if name == settings.vision_model else None,
            })
        names = {m["name"] for m in installed}
        return {"chat_model": settings.chat_model, "vision_model": settings.vision_model,
                "installed": installed,
                "suggested": [s for s in SUGGESTED_MODELS if s["name"] not in names]}

    async def _known(name: str) -> None:
        try:
            tags = await _ollama("/api/tags")
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=f"Ollama não respondeu: {exc}")
        if name not in {m.get("name") for m in tags.get("models", [])}:
            raise HTTPException(status_code=404, detail=f"Modelo {name} não está instalado. "
                                                        f"Rode: ollama pull {name}")

    @app.put("/api/models/chat")
    async def set_chat_model(body: ChatModelIn):
        """Troca o cérebro da Sexta-feira por outro modelo instalado (fica salvo no PC)."""
        await _known(body.name)
        settings.chat_model = body.name
        store.set_prefs({"chat_model": body.name})
        return {"chat_model": settings.chat_model}

    @app.post("/api/models/{name:path}/unload")
    async def unload(name: str):
        if not MODEL_NAME.match(name):
            raise HTTPException(status_code=422, detail="Nome inválido.")
        try:
            await _ollama("/api/generate", "POST", json={"model": name, "keep_alive": 0}, timeout=30)
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=f"Não consegui liberar: {exc}")
        return {"ok": True}

    @app.post("/api/models/{name:path}/load")
    async def load(name: str):
        if not MODEL_NAME.match(name):
            raise HTTPException(status_code=422, detail="Nome inválido.")
        await _known(name)
        try:
            await _ollama("/api/generate", "POST", timeout=300,
                          json={"model": name, "prompt": "", "keep_alive": f"{settings.idle_minutes}m"})
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=f"Não consegui carregar: {exc}")
        return {"ok": True}

    @app.get("/api/logs")
    async def logs(lines: int = 200, q: str | None = None):
        path = log_dir / "servidor.log"
        return {"file": str(path), "lines": await asyncio.to_thread(tail, path, lines, q)}
