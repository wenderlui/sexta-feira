"""Servidor da Sexta-feira: API do painel + app web do iPad."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from . import providers
from .cache import TTLCache
from .config import Settings

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


def create_app(
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    web_dir: Path = WEB_DIR,
) -> FastAPI:
    settings = settings or Settings.from_env()
    cache = TTLCache()
    state: dict[str, httpx.AsyncClient] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        own = client is None
        state["client"] = client or httpx.AsyncClient(
            headers={"User-Agent": "sexta-feira/0.1"}
        )
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
