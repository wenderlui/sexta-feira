"""Vigia das câmeras: pessoa ou carro de madrugada vira alerta no painel."""
import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sexta.cameras import in_window, parse_vision

TZ = ZoneInfo("America/New_York")


def token(client):
    return client.get("/api/cameras/rule").json()["webhook_token"]


def connect_ha(client):
    client.put("/api/connections/homeassistant",
               json={"values": {"url": "http://ha.local:8123", "token": "tok-ha-1234"}})


def vision_says(upstream, text):
    upstream.ollama_replies.append({"role": "assistant", "content": text})


def test_time_window_crosses_midnight():
    assert in_window(time(2, 30), "00:00", "05:00")
    assert not in_window(time(5, 0), "00:00", "05:00")
    assert in_window(time(23, 30), "22:00", "05:00") and in_window(time(1, 0), "22:00", "05:00")
    assert not in_window(time(12, 0), "22:00", "05:00")


def test_parse_vision_tolerates_extra_text():
    v = parse_vision('Claro! {"pessoa": true, "carro": false, "descricao": "Homem de boné no portão"} fim')
    assert v["pessoa"] and not v["carro"] and v["descricao"] == "Homem de boné no portão"
    assert parse_vision("não sei")["pessoa"] is False


def test_webhook_requires_token(client):
    r = client.post("/api/cameras/event", json={"camera": "camera.garagem"})
    assert r.status_code == 401
    r = client.post("/api/cameras/event", json={"camera": "camera.garagem"}, headers={"X-Sexta-Token": "chute"})
    assert r.status_code == 401


def test_token_is_stable_and_saved(client, store):
    t = token(client)
    assert len(t) >= 24 and token(client) == t
    assert store.prefs["webhook_token"] == t


def test_person_at_night_creates_alert_with_photo(client, upstream, monkeypatch):
    import sexta.cameras as cam
    connect_ha(client)
    monkeypatch.setattr(cam, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: datetime(2026, 11, 8, 2, 14, tzinfo=TZ))}))
    vision_says(upstream, '{"pessoa": true, "carro": false, "descricao": "Uma pessoa perto do portão"}')
    r = client.post("/api/cameras/event", json={"camera": "camera.blink_garagem"}, headers={"X-Sexta-Token": token(client)})
    body = r.json()
    assert body["alerta"] is True and body["objetos"] == ["pessoa"]
    # a foto foi pedida ao Home Assistant e mandada para o modelo de visão
    assert upstream.ollama_bodies[-1]["model"] == "qwen2.5vl:7b"
    assert upstream.ollama_bodies[-1]["messages"][0]["images"]
    alerts = client.get("/api/alerts").json()["alerts"]
    assert alerts[0]["descricao"] == "Uma pessoa perto do portão" and alerts[0]["visto"] is False
    photo = client.get(f"/api/alerts/{alerts[0]['id']}.jpg")
    assert photo.status_code == 200 and photo.content.startswith(b"\xff\xd8")
    assert client.post(f"/api/alerts/{alerts[0]['id']}/ack").status_code == 200
    assert client.get("/api/alerts").json()["alerts"][0]["visto"] is True


def test_daytime_motion_is_ignored_without_calling_ai(client, upstream, monkeypatch):
    import sexta.cameras as cam
    connect_ha(client)
    monkeypatch.setattr(cam, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: datetime(2026, 11, 8, 14, 0, tzinfo=TZ))}))
    r = client.post("/api/cameras/event", json={"camera": "camera.blink_garagem"}, headers={"X-Sexta-Token": token(client)})
    assert r.json()["alerta"] is False and "fora do horário" in r.json()["motivo"]
    assert upstream.ollama_bodies == []
    assert client.get("/api/alerts").json()["alerts"] == []


def test_cat_at_night_is_not_an_alert(client, upstream, monkeypatch):
    import sexta.cameras as cam
    connect_ha(client)
    monkeypatch.setattr(cam, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: datetime(2026, 11, 8, 3, 0, tzinfo=TZ))}))
    vision_says(upstream, '{"pessoa": false, "carro": false, "animal": true, "descricao": "Um gato"}')
    r = client.post("/api/cameras/event", json={"camera": "camera.blink_quintal"}, headers={"X-Sexta-Token": token(client)})
    assert r.json()["alerta"] is False


def test_rule_can_be_changed_and_is_validated(client):
    assert client.put("/api/cameras/rule", json={"start": "22:00", "objects": ["pessoa"]}).json()["start"] == "22:00"
    assert client.put("/api/cameras/rule", json={"start": "25:99"}).status_code == 422
    assert client.put("/api/cameras/rule", json={"objects": ["ovni"]}).status_code == 422


def test_camera_name_and_photo_id_are_validated(client):
    t = token(client)
    bad = client.post("/api/cameras/event", json={"camera": "../../etc"}, headers={"X-Sexta-Token": t})
    assert bad.status_code == 422
    assert client.get("/api/alerts/..%2f..%2fajustes.jpg").status_code == 404
