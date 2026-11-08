def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_weather_lowell(client, upstream):
    r = client.get("/api/weather")
    assert r.status_code == 200
    w = r.json()
    assert w["city"] == "Lowell, MA"
    assert w["temperature"] == 8.4
    assert w["description"] == "Nublado"
    assert [d["description"] for d in w["days"]] == ["Nublado", "Chuva fraca", "Céu limpo"]
    assert w["days"][0]["sunset"] == "2026-11-07T16:24"
    req = upstream.last_request["api.open-meteo.com"]
    assert req.url.params["latitude"] == "42.6334"
    assert req.url.params["timezone"] == "America/New_York"


def test_crypto_has_all_requested_coins_in_order(client):
    c = client.get("/api/crypto").json()
    assert [x["symbol"] for x in c["coins"]] == ["BTC", "ETH", "POL", "UNI", "DOT", "LINK"]
    pol = c["coins"][2]
    assert pol["usd"] == 0.2345 and pol["brl"] == 1.27
    assert c["usdt_brl"] == 5.41


def test_crypto_is_cached(client, upstream):
    first = client.get("/api/crypto").json()
    second = client.get("/api/crypto").json()
    assert first["cached"] is False
    assert second["cached"] is True
    assert upstream.calls["api.coingecko.com"] == 1


def test_coingecko_key_is_sent_when_configured(upstream, store):
    import httpx
    from fastapi.testclient import TestClient

    from conftest import FakeEars, FakeMouth
    from sexta.app import create_app
    from sexta.config import Settings

    http = httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler))
    # Um Transcriber falso evita carregar o Whisper de verdade durante o teste.
    app = create_app(settings=Settings(coingecko_api_key="CG-teste"), client=http,
                     transcriber=FakeEars(), speaker=FakeMouth(), store=store)
    with TestClient(app) as c:
        c.get("/api/crypto")
    assert upstream.last_request["api.coingecko.com"].headers["x-cg-demo-api-key"] == "CG-teste"


def test_usdtbrl_from_binance(client):
    u = client.get("/api/usdtbrl").json()
    assert u["price"] == 5.423
    assert u["source"] == "Binance"


def test_usdtbrl_falls_back_to_coingecko_when_binance_blocks_us(client, upstream):
    upstream.binance_status = 451  # bloqueio geográfico da Binance para IPs dos EUA
    u = client.get("/api/usdtbrl").json()
    assert u["price"] == 5.41
    assert u["source"] == "CoinGecko"
    # A reserva reaproveita o cache do painel de cripto: nenhuma chamada extra.
    client.get("/api/crypto")
    assert upstream.calls["api.coingecko.com"] == 1


def test_upstream_down_returns_502(client, upstream):
    upstream.fail.add("api.open-meteo.com")
    r = client.get("/api/weather")
    assert r.status_code == 502


def test_config_lists_coins(client):
    cfg = client.get("/api/config").json()
    assert cfg["coins"] == ["BTC", "ETH", "POL", "UNI", "DOT", "LINK"]
    assert cfg["refresh_seconds"]["crypto"] == 300


def test_serves_ipad_app(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Sexta-feira" in r.text
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/sw.js").status_code == 200


def test_ipad_diagnostic_log(client, caplog):
    with caplog.at_level("INFO", logger="sexta.ipad"):
        r = client.post("/api/log", json={"msg": "escuta ligada"})
    assert r.status_code == 200
    assert "escuta ligada" in caplog.text


def test_web_files_are_revalidated(client):
    assert client.get("/voice.js").headers["cache-control"] == "no-cache"
