import json

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from sexta.app import create_app
from sexta.config import Settings

WEATHER = {
    "current": {
        "temperature_2m": 8.4,
        "apparent_temperature": 5.9,
        "relative_humidity_2m": 71,
        "weather_code": 3,
        "wind_speed_10m": 14.2,
    },
    "daily": {
        "time": ["2026-11-07", "2026-11-08", "2026-11-09"],
        "weather_code": [3, 61, 0],
        "temperature_2m_max": [11.0, 9.5, 12.1],
        "temperature_2m_min": [2.0, 4.1, 1.3],
        "precipitation_probability_max": [10, 80, 0],
        "sunrise": ["2026-11-07T06:28", "2026-11-08T06:29", "2026-11-09T06:31"],
        "sunset": ["2026-11-07T16:24", "2026-11-08T16:23", "2026-11-09T16:22"],
    },
}

CRYPTO = {
    "bitcoin": {"usd": 101000.5, "brl": 545000.0, "usd_24h_change": 1.5},
    "ethereum": {"usd": 3500.0, "brl": 18900.0, "usd_24h_change": -2.1},
    "polygon-ecosystem-token": {"usd": 0.2345, "brl": 1.27, "usd_24h_change": 0.3},
    "uniswap": {"usd": 7.1, "brl": 38.3, "usd_24h_change": 0.0},
    "polkadot": {"usd": 3.2, "brl": 17.3, "usd_24h_change": 4.0},
    "chainlink": {"usd": 14.5, "brl": 78.3, "usd_24h_change": -0.5},
    "tether": {"usd": 1.0, "brl": 5.41, "brl_24h_change": 0.12},
}


class FakeUpstream:
    """Simula Open-Meteo, CoinGecko e Binance e conta as chamadas."""

    def __init__(self):
        self.calls: dict[str, int] = {}
        self.fail: set[str] = set()
        self.binance_status = 200
        self.last_request: dict[str, httpx.Request] = {}
        # Respostas do Ollama, em ordem; cada uma é o "message" devolvido.
        self.ollama_replies: list[dict] = []
        self.ollama_bodies: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        self.calls[host] = self.calls.get(host, 0) + 1
        self.last_request[host] = request
        if host in self.fail:
            return httpx.Response(503)
        if host == "api.open-meteo.com":
            return httpx.Response(200, json=WEATHER)
        if host == "api.coingecko.com":
            ids = request.url.params["ids"].split(",")
            return httpx.Response(200, json={k: v for k, v in CRYPTO.items() if k in ids})
        if host == "127.0.0.1" and request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
        if host == "127.0.0.1" and request.url.path == "/api/chat":
            self.ollama_bodies.append(json.loads(request.content))
            msg = self.ollama_replies.pop(0) if self.ollama_replies else {
                "role": "assistant", "content": "Olá, Wender."}
            return httpx.Response(200, json={"message": msg, "done": True})
        if host == "api.binance.com":
            if self.binance_status != 200:
                return httpx.Response(self.binance_status, json={"code": 0, "msg": "restricted"})
            return httpx.Response(200, json={"symbol": "USDTBRL", "price": "5.4230"})
        return httpx.Response(404)


@pytest.fixture
def upstream():
    return FakeUpstream()


class FakeSearch:
    def __init__(self):
        self.queries: list[str] = []

    async def __call__(self, query: str):
        self.queries.append(query)
        return [{"title": "Resultado", "body": "Flamengo venceu por 2 a 1.",
                 "href": "https://exemplo.com/jogo"}]


class FakeEars:
    available = True
    error = None

    async def transcribe(self, audio: bytes):
        return {"text": "qual a temperatura agora", "duration": 1.2}


@pytest.fixture
def search():
    return FakeSearch()


@pytest.fixture
def client(upstream, search):
    http = httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler))
    app = create_app(settings=Settings(), client=http, search=search, transcriber=FakeEars())
    with TestClient(app) as c:
        yield c
