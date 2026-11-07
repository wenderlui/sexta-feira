"""Servidor da Sexta-feira: API do painel + app web do iPad."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles

from . import providers, system
from .assistant import Assistant, wants_vision
from .cache import TTLCache
from .config import Settings
from .speech import Transcriber


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    image: str | None = None  # JPEG em base64 (sem o prefixo data:)

class ClientLog(BaseModel):
    msg: str


def _setup_logging() -> None:
    log = logging.getLogger("sexta")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)


WEB_DIR = Path(__file__).resolve().parents[2] / "web"


def create_app(
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    web_dir: Path = WEB_DIR,
    search=None,
    news=None,
    transcriber: Transcriber | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    _setup_logging()
    cache = TTLCache()
    state: dict = {}
    ears = transcriber or Transcriber(settings)

    async def _warm():
        log = logging.getLogger("sexta")
        try:
            await state["assistant"].warm_up()
            log.info("Modelo %s carregado na GPU", settings.chat_model)
        except Exception as exc:  # Ollama ainda subindo etc.: não impede o painel
            log.warning("IA não pré-carregou: %s", exc)
        if transcriber is None:
            try:
                await ears.warm_up()
            except Exception as exc:
                log.warning("Whisper não carregou: %s", exc)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        own = client is None
        state["client"] = client or httpx.AsyncClient(
            headers={"User-Agent": "sexta-feira/0.1"}
        )
        kwargs = {k: v for k, v in (("search", search), ("news", news)) if v}
        state["assistant"] = Assistant(state["client"], settings, **kwargs)
        if client is None:
            # Carrega a IA e o Whisper em segundo plano para a primeira resposta não demorar.
            state["warm"] = asyncio.create_task(_warm())
        try:
            yield
        finally:
            if own:
                await state["client"].aclose()

    app = FastAPI(title="Sexta-feira", version="0.1.0", lifespan=lifespan)

    async def _serve(key: str, ttl: int, fetch):
        try:
            value, cached = await cache.get_or_fetch(
                key, ttl, lambda: fetch(state["client"], settings)
            )
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=502, detail=f"Falha ao buscar {key}: {exc}")
        return {**value, "cached": cached}

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/weather")
    async def weather():
        return await _serve("weather", settings.weather_ttl, providers.fetch_weather)

    @app.get("/api/crypto")
    async def crypto():
        return await _serve("crypto", settings.crypto_ttl, providers.fetch_crypto)

    @app.get("/api/usdtbrl")
    async def usdtbrl():
        try:
            return await _serve(
                "usdtbrl",
                settings.usdtbrl_ttl,
                lambda c, _s: providers.fetch_binance_usdtbrl(c),
            )
        except HTTPException:
            # Binance indisponível (ex.: bloqueio nos EUA): usa o Tether do CoinGecko.
            crypto_data = await _serve("crypto", settings.crypto_ttl, providers.fetch_crypto)
            try:
                return {**providers.usdtbrl_from_crypto(crypto_data),
                        "cached": crypto_data["cached"]}
            except (KeyError, ValueError, TypeError) as exc:
                raise HTTPException(status_code=502, detail=f"Sem USDT/BRL: {exc}")

    async def _panel() -> dict:
        """Dados do painel para dar contexto à IA (o que falhar fica de fora)."""
        out = {}
        for key, fn in (("weather", weather), ("crypto", crypto), ("usdtbrl", usdtbrl)):
            try:
                out[key] = await fn()
            except HTTPException:
                pass
        return out

    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        history = [m.model_dump() for m in req.messages]
        image = req.image if req.image and wants_vision(history[-1]["content"]) else None
        try:
            return await state["assistant"].reply(history, await _panel(), image_b64=image)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Não consegui falar com o Ollama em {settings.ollama_url}: {exc}",
            )

    @app.post("/api/transcribe")
    async def transcribe(request: Request):
        if not ears.available:
            raise HTTPException(status_code=503, detail=ears.error)
        audio = await request.body()
        if not audio:
            raise HTTPException(status_code=400, detail="Áudio vazio.")
        if len(audio) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Áudio muito grande.")
        try:
            result = await ears.transcribe(audio)
        except Exception as exc:
            logging.getLogger("sexta").exception("Falha ao transcrever")
            raise HTTPException(status_code=500, detail=f"Falha ao transcrever: {exc}")
        logging.getLogger("sexta").info(
            "Ouvi (%s, %d bytes): %r", request.headers.get("content-type"), len(audio),
            result.get("text", ""))
        return result

    @app.post("/api/log")
    async def client_log(entry: ClientLog):
        # Diagnóstico do iPad: aparece no logs/servidor.log do PC.
        logging.getLogger("sexta.ipad").info("%s", entry.msg[:500])
        return {"ok": True}

    @app.get("/api/assistant/status")
    async def assistant_status():
        return {**await state["assistant"].status(),
                "chat_model": settings.chat_model,
                "vision_model": settings.vision_model,
                "stt_available": ears.available}

    @app.get("/api/system")
    async def system_stats():
        return await system.snapshot()

    @app.get("/api/config")
    async def config():
        return {
            "city": settings.city_name,
            "coins": list(settings.coins.keys()),
            "refresh_seconds": {
                "weather": settings.weather_ttl,
                "crypto": settings.crypto_ttl,
                "usdtbrl": settings.usdtbrl_ttl,
            },
        }

    if web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


app = create_app()
