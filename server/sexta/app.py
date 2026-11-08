"""Servidor da Sexta-feira: API do painel + app web do iPad."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles

from . import providers, system
from .assistant import Assistant, wants_vision
from .cache import TTLCache
from .config import Settings
from .speech import Transcriber
from .tts import Speaker
from .store import Store
from .home import CATALOG, CATALOG_BY_ID, Home, HomeError


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    image: str | None = None  # JPEG em base64 (sem o prefixo data:)

class TtsRequest(BaseModel):
    text: str


EDGE_VOICES = {
    "pt-BR-FranciscaNeural": "Francisca (feminina)",
    "pt-BR-ThalitaMultilingualNeural": "Thalita (feminina)",
    "pt-BR-AntonioNeural": "Antonio (masculina)",
}
KOKORO_VOICES = {"pf_dora": "Dora (feminina)", "pm_alex": "Alex (masculina)", "pm_santa": "Santa (masculina)"}


class Prefs(BaseModel):
    tts_engine: str | None = Field(default=None, pattern="^(edge|kokoro)$")
    edge_voice: str | None = None
    tts_voice: str | None = None
    tts_speed: float | None = Field(default=None, ge=0.8, le=1.3)


class ConnectionIn(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class DeviceAction(BaseModel):
    action: str = Field(pattern="^(ligar|desligar|alternar|brilho|temperatura)$")
    value: float | None = None


class ClientLog(BaseModel):
    msg: str


def _setup_logging() -> None:
    log = logging.getLogger("sexta")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def _keep_last_audio(audio: bytes, content_type: str) -> None:
    # Guarda só o último áudio recebido, no próprio PC, para diagnóstico (logs/ não vai pro Git).
    if not LOG_DIR.is_dir():
        return
    ext = "webm" if "webm" in content_type else "wav" if "wav" in content_type else "mp4"
    try:
        (LOG_DIR / f"ultimo-audio.{ext}").write_bytes(audio)
    except OSError:
        pass


def _apply_prefs(settings: Settings, prefs: dict) -> None:
    for key in ("tts_engine", "edge_voice", "tts_voice", "tts_speed"):
        if prefs.get(key) is not None:
            setattr(settings, key, prefs[key])


WEB_DIR = Path(__file__).resolve().parents[2] / "web"


def create_app(
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    web_dir: Path = WEB_DIR,
    search=None,
    news=None,
    transcriber: Transcriber | None = None,
    speaker: Speaker | None = None,
    store: Store | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    store = store or Store()
    _apply_prefs(settings, store.prefs)
    _setup_logging()
    cache = TTLCache()
    state: dict = {}
    ears = transcriber or Transcriber(settings)
    mouth = speaker or Speaker(settings)

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
        if speaker is None:
            try:
                await mouth.warm_up()
                if mouth.available:
                    log.info("Voz pronta: %s", mouth.last_engine)
            except Exception as exc:
                log.warning("Voz não carregou: %s", exc)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        own = client is None
        state["client"] = client or httpx.AsyncClient(
            headers={"User-Agent": "sexta-feira/0.1"}
        )
        kwargs = {k: v for k, v in (("search", search), ("news", news)) if v}
        state["home"] = Home(state["client"], store)
        state["assistant"] = Assistant(state["client"], settings, home=state["home"], **kwargs)
        if client is None:
            # Carrega a IA e o Whisper em segundo plano para a primeira resposta não demorar.
            state["warm"] = asyncio.create_task(_warm())
        try:
            yield
        finally:
            if own:
                await state["client"].aclose()

    app = FastAPI(title="Sexta-feira", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def no_stale_web(request: Request, call_next):
        # O iPad guarda arquivos em cache por conta própria; "no-cache" o obriga a
        # conferir com o PC (resposta 304 rápida quando nada mudou).
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        else:
            response.headers["Cache-Control"] = "no-store"
        # Cabeçalhos de segurança padrão.
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
        return response

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
            "Ouvi (%s, %d bytes, %ss): %r", request.headers.get("content-type"), len(audio),
            result.get("duration"), result.get("text", ""))
        _keep_last_audio(audio, request.headers.get("content-type", ""))
        return result

    @app.post("/api/tts")
    async def tts(req: TtsRequest):
        if not mouth.available:
            raise HTTPException(status_code=503, detail=mouth.error)
        text = req.text.strip()[:1500]
        if not text:
            raise HTTPException(status_code=400, detail="Texto vazio.")
        try:
            audio, media_type = await mouth.speak(text)
        except Exception as exc:
            logging.getLogger("sexta").exception("Falha ao gerar a voz")
            raise HTTPException(status_code=500, detail=f"Falha ao gerar a voz: {exc}")
        return Response(content=audio, media_type=media_type,
                        headers={"X-Sexta-Voz": getattr(mouth, "last_engine", None) or "?"})

    # ---------------- Ajustes (salvos no PC, em data/ajustes.json) ----------------
    def _prefs_view() -> dict:
        return {
            "tts_engine": settings.tts_engine, "edge_voice": settings.edge_voice,
            "tts_voice": settings.tts_voice, "tts_speed": settings.tts_speed,
            "options": {"edge_voice": EDGE_VOICES, "tts_voice": KOKORO_VOICES},
            "saved_at": str(store.path.name),
        }

    @app.get("/api/settings")
    async def get_settings():
        return _prefs_view()

    @app.put("/api/settings")
    async def put_settings(p: Prefs):
        values = {k: v for k, v in p.model_dump().items() if v is not None}
        if "edge_voice" in values and values["edge_voice"] not in EDGE_VOICES:
            raise HTTPException(status_code=422, detail="Voz desconhecida.")
        if "tts_voice" in values and values["tts_voice"] not in KOKORO_VOICES:
            raise HTTPException(status_code=422, detail="Voz desconhecida.")
        store.set_prefs(values)
        _apply_prefs(settings, values)
        return _prefs_view()

    @app.get("/api/connections")
    async def list_connections():
        ha_on = bool(store.connection("homeassistant").get("token"))
        out = []
        for c in CATALOG:
            saved = store.public_connection(c["id"])
            if c["kind"] == "native":
                status = "on" if saved else "off"
            elif c["kind"] == "via_ha":
                status = "via_ha_on" if ha_on else "via_ha_off"
            else:
                status = "soon"
            out.append({**c, "status": status, "saved": saved})
        return {"connections": out}

    @app.put("/api/connections/{cid}")
    async def save_connection(cid: str, body: ConnectionIn):
        meta = CATALOG_BY_ID.get(cid)
        if not meta or meta["kind"] != "native":
            raise HTTPException(status_code=404, detail="Conexão desconhecida.")
        allowed = {f["key"]: f for f in meta["fields"]}
        values = {}
        for k, v in body.values.items():
            if k not in allowed:
                raise HTTPException(status_code=422, detail=f"Campo desconhecido: {k}")
            v = v.strip()
            if len(v) > 2000:
                raise HTTPException(status_code=422, detail=f"{k} muito longo")
            if allowed[k]["type"] == "url" and v and not v.startswith(("http://", "https://")):
                raise HTTPException(status_code=422, detail="O endereço precisa começar com http:// ou https://")
            values[k] = v.rstrip("/") if allowed[k]["type"] == "url" else v
        store.set_connection(cid, values)
        try:
            detail = await state["home"].check(cid)
            ok = True
        except HomeError as exc:
            detail, ok = str(exc), False
        return {"ok": ok, "detail": detail, "saved": store.public_connection(cid)}

    @app.delete("/api/connections/{cid}")
    async def delete_connection(cid: str):
        if cid not in CATALOG_BY_ID:
            raise HTTPException(status_code=404, detail="Conexão desconhecida.")
        store.remove_connection(cid)
        return {"ok": True}

    @app.get("/api/home/devices")
    async def home_devices():
        devices, errors = await state["home"].devices()
        return {"devices": devices, "errors": errors}

    @app.post("/api/home/devices/{device_id:path}")
    async def home_action(device_id: str, body: DeviceAction):
        try:
            await state["home"].act(device_id, body.action, body.value)
        except HomeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True}

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
                "stt_available": ears.available,
                "tts_available": mouth.available}

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
