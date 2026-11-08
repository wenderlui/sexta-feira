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


HA_STATES = [
    {"entity_id": "light.sala", "state": "off", "attributes": {"friendly_name": "Luz da sala"}},
    {"entity_id": "media_player.tv_samsung", "state": "on", "attributes": {"friendly_name": "TV Samsung"}},
    {"entity_id": "climate.ar_quarto", "state": "cool", "attributes": {"friendly_name": "Ar do quarto"}},
    {"entity_id": "sensor.temperatura", "state": "21", "attributes": {}},
    {"entity_id": "switch.velha", "state": "unavailable", "attributes": {}},
]


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
        self.ha_calls: list = []
        self.ollama_generate: list[dict] = []
        self.ollama_loaded: list[str] = []
        self.govee_calls: list = []

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
        if host == "127.0.0.1" and request.url.path == "/api/generate":
            self.ollama_generate.append(json.loads(request.content))
            return httpx.Response(200, json={"done": True})
        if host == "127.0.0.1" and request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": m} for m in self.ollama_loaded]})
        if host == "127.0.0.1" and request.url.path == "/api/chat":
            self.ollama_bodies.append(json.loads(request.content))
            msg = self.ollama_replies.pop(0) if self.ollama_replies else {
                "role": "assistant", "content": "Olá, Wender."}
            return httpx.Response(200, json={"message": msg, "done": True})
        if host == "exemplo.com":
            page = "<html><body><nav>menu</nav><article><p>" + "O Flamengo venceu o jogo por 2 a 1 no Maracanã. " * 10 + "</p></article></body></html>"
            return httpx.Response(200, text=page, headers={"content-type": "text/html; charset=utf-8"})
        if host == "ha.local":
            if request.headers.get("authorization") != "Bearer tok-ha-1234":
                return httpx.Response(401)
            if request.url.path == "/api/":
                return httpx.Response(200, json={"message": "API running."})
            if request.url.path == "/api/states":
                return httpx.Response(200, json=HA_STATES)
            if request.url.path.startswith("/api/camera_proxy/"):
                return httpx.Response(200, content=b"\xff\xd8JPEG-FALSO\xff\xd9",
                                      headers={"content-type": "image/jpeg"})
            if request.url.path.startswith("/api/services/"):
                self.ha_calls.append((request.url.path, json.loads(request.content)))
                return httpx.Response(200, json=[])
        if host == "openapi.api.govee.com":
            if request.headers.get("govee-api-key") != "gv-key-9876":
                return httpx.Response(401)
            if request.url.path.endswith("/user/devices"):
                return httpx.Response(200, json={"code": 200, "data": [
                    {"sku": "H6199", "device": "AA:BB", "deviceName": "LED do quarto", "type": "light"}]})
            if request.url.path.endswith("/device/control"):
                self.govee_calls.append(json.loads(request.content))
                return httpx.Response(200, json={"code": 200})
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
    loaded = False
    last_used = 0.0
    warmed = 0

    async def warm_up(self):
        self.warmed += 1
        self.loaded = True

    async def transcribe(self, audio: bytes):
        return {"text": "qual a temperatura agora", "duration": 1.2}


class FakeMouth:
    available = True
    error = None

    def __init__(self):
        self.said = []

    async def speak(self, text: str) -> bytes:
        self.said.append(text)
        return b"RIFF....WAVEfmt ", "audio/wav"


@pytest.fixture
def search():
    return FakeSearch()


class FakeNews(FakeSearch):
    async def __call__(self, query: str):
        self.queries.append(query)
        return [{"title": "Copom mantém juros", "body": "Decisão unânime.", "source": "g1",
                 "date": "2026-11-07", "href": "https://g1.globo.com/economia/copom"}]


@pytest.fixture
def news():
    return FakeNews()


@pytest.fixture
def store(tmp_path):
    from sexta.store import Store
    return Store(tmp_path / "ajustes.json")


@pytest.fixture
def alerts(tmp_path):
    from sexta.cameras import Alerts
    return Alerts(tmp_path / "alertas")


@pytest.fixture
def client(upstream, search, news, store, alerts):
    http = httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler))
    app = create_app(settings=Settings(), client=http, search=search, news=news,
                     transcriber=FakeEars(), speaker=FakeMouth(), store=store, alerts=alerts)
    with TestClient(app) as c:
        yield c
