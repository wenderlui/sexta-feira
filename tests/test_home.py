"""Ajustes, conexões da casa e segurança."""
import json

from sexta.home import best_match
from sexta.store import Store


def connect_ha(client):
    return client.put("/api/connections/homeassistant",
                      json={"values": {"url": "http://ha.local:8123/", "token": "tok-ha-1234"}})


def test_preferences_are_saved_on_the_pc(client, store):
    r = client.put("/api/settings", json={"edge_voice": "pt-BR-AntonioNeural", "tts_speed": 1.1})
    assert r.status_code == 200 and r.json()["edge_voice"] == "pt-BR-AntonioNeural"
    saved = json.loads(store.path.read_text(encoding="utf-8"))
    assert saved["prefs"] == {"edge_voice": "pt-BR-AntonioNeural", "tts_speed": 1.1}
    # Reabrindo o arquivo (como depois de reiniciar o PC) o valor continua lá.
    assert Store(store.path).prefs["edge_voice"] == "pt-BR-AntonioNeural"
    assert client.get("/api/settings").json()["tts_speed"] == 1.1


def test_preferences_are_validated(client):
    assert client.put("/api/settings", json={"edge_voice": "voz-inventada"}).status_code == 422
    assert client.put("/api/settings", json={"tts_speed": 5}).status_code == 422
    assert client.put("/api/settings", json={"tts_engine": "rm -rf"}).status_code == 422


def test_connection_secret_never_goes_back_to_the_ipad(client, store):
    r = connect_ha(client)
    assert r.json()["ok"] is True
    assert r.json()["saved"]["token"] == "••••1234"
    everything = client.get("/api/connections").text
    assert "tok-ha-1234" not in everything
    assert store.connection("homeassistant")["token"] == "tok-ha-1234"
    assert store.connection("homeassistant")["url"] == "http://ha.local:8123"


def test_empty_secret_keeps_the_saved_one(client, store):
    connect_ha(client)
    client.put("/api/connections/homeassistant", json={"values": {"url": "http://ha.local:8123", "token": ""}})
    assert store.connection("homeassistant")["token"] == "tok-ha-1234"


def test_wrong_token_is_reported(client):
    r = client.put("/api/connections/homeassistant",
                   json={"values": {"url": "http://ha.local:8123", "token": "errado"}})
    assert r.json()["ok"] is False and "token" in r.json()["detail"]


def test_connection_input_is_validated(client):
    bad_url = client.put("/api/connections/homeassistant", json={"values": {"url": "file:///etc/passwd"}})
    assert bad_url.status_code == 422
    assert client.put("/api/connections/homeassistant", json={"values": {"admin": "1"}}).status_code == 422
    assert client.put("/api/connections/banco", json={"values": {}}).status_code == 404
    assert client.put("/api/connections/../../x", json={"values": {}}).status_code in (404, 405)


def test_catalog_shows_status(client):
    before = {c["id"]: c["status"] for c in client.get("/api/connections").json()["connections"]}
    assert before["homeassistant"] == "off" and before["samsung_tv"] == "via_ha_off" and before["banco"] == "soon"
    connect_ha(client)
    after = {c["id"]: c["status"] for c in client.get("/api/connections").json()["connections"]}
    assert after["homeassistant"] == "on" and after["blink"] == "via_ha_on"


def test_devices_from_home_assistant_and_govee(client, upstream):
    connect_ha(client)
    client.put("/api/connections/govee", json={"values": {"api_key": "gv-key-9876"}})
    devices = client.get("/api/home/devices").json()["devices"]
    names = {d["name"]: d for d in devices}
    assert set(names) == {"Luz da sala", "TV Samsung", "Ar do quarto", "LED do quarto"}
    assert names["TV Samsung"]["on"] is True and names["Luz da sala"]["on"] is False

    assert client.post("/api/home/devices/ha:light.sala", json={"action": "ligar"}).status_code == 200
    assert upstream.ha_calls[-1] == ("/api/services/light/turn_on", {"entity_id": "light.sala"})
    client.post("/api/home/devices/ha:climate.ar_quarto", json={"action": "temperatura", "value": 40})
    assert upstream.ha_calls[-1][1]["temperature"] == 30  # limitado a 30 °C
    client.post("/api/home/devices/govee:H6199:AA:BB", json={"action": "desligar"})
    assert upstream.govee_calls[-1]["payload"]["capability"]["value"] == 0


def test_device_actions_are_validated(client, upstream):
    connect_ha(client)
    assert client.post("/api/home/devices/ha:light.sala", json={"action": "explodir"}).status_code == 422
    assert client.post("/api/home/devices/ha:light.sala;rm", json={"action": "ligar"}).status_code == 400
    assert client.post("/api/home/devices/ha:sensor.temperatura", json={"action": "ligar"}).status_code == 400
    assert upstream.ha_calls == []


def test_ai_controls_the_house(client, upstream):
    connect_ha(client)
    upstream.ollama_replies = [
        {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "controlar_casa", "arguments": {"dispositivo": "luz da sala", "acao": "ligar"}}}]},
        {"role": "assistant", "content": "Pronto, acendi a luz da sala."},
    ]
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "acende a luz da sala"}]})
    assert r.json()["text"] == "Pronto, acendi a luz da sala."
    assert upstream.ha_calls[-1] == ("/api/services/light/turn_on", {"entity_id": "light.sala"})
    tools = [t["function"]["name"] for t in upstream.ollama_bodies[0]["tools"]]
    assert "controlar_casa" in tools


def test_home_tool_hidden_until_connected(client, upstream):
    client.post("/api/chat", json={"messages": [{"role": "user", "content": "oi"}]})
    tools = [t["function"]["name"] for t in upstream.ollama_bodies[0]["tools"]]
    assert "controlar_casa" not in tools


def test_best_match_understands_spoken_names():
    devices = [
        {"id": "ha:light.sala", "name": "Luz da sala", "kind": "luz"},
        {"id": "ha:light.quarto", "name": "Abajur do quarto", "kind": "luz"},
        {"id": "ha:media_player.tv", "name": "Samsung", "kind": "tv"},
    ]
    assert best_match(devices, "luz da sala")["id"] == "ha:light.sala"
    assert best_match(devices, "lâmpada do quarto")["id"] == "ha:light.quarto"
    assert best_match(devices, "televisão")["id"] == "ha:media_player.tv"
    assert best_match(devices, "da do") is None


def test_corrupted_settings_file_is_recovered(tmp_path):
    path = tmp_path / "ajustes.json"
    path.write_text("{ isto não é json", encoding="utf-8")
    s = Store(path)
    assert s.prefs == {}
    assert (tmp_path / "ajustes.corrompido.json").exists()


def test_security_headers(client):
    for url in ("/", "/api/health"):
        h = client.get(url).headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer"
    assert client.get("/api/settings").headers["cache-control"] == "no-store"


def test_static_files_cannot_escape_web_folder(client):
    for path in ("/../server/sexta/app.py", "/%2e%2e/server/sexta/app.py", "/..%2f.env"):
        r = client.get(path)
        assert r.status_code == 404 or "def create_app" not in r.text
