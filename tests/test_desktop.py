import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))


def test_services_lists_every_piece(client, upstream):
    upstream.ollama_loaded = ["qwen3:8b"]
    d = client.get("/api/desktop/services").json()
    ids = [s["id"] for s in d["services"]]
    assert ids == ["servidor", "ollama", "whisper", "voz", "internet", "homeassistant", "tailscale"]
    ollama = next(s for s in d["services"] if s["id"] == "ollama")
    assert ollama["ok"] is True and ollama["loaded"] == ["qwen3:8b"]
    assert d["chat_model"] == "qwen3:8b" and d["offline"] is False


def test_offline_mode_skips_internet_and_web_tools(client, upstream):
    assert client.put("/api/settings", json={"offline": True}).json()["offline"] is True
    d = client.get("/api/desktop/services").json()
    net = next(s for s in d["services"] if s["id"] == "internet")
    assert net["ok"] is None and "www.gstatic.com" not in upstream.calls
    assert next(s for s in d["services"] if s["id"] == "voz")["detail"] == "kokoro"
    client.post("/api/chat", json={"messages": [{"role": "user", "content": "oi"}]})
    assert "tools" not in upstream.ollama_bodies[-1]
    # Volta ao normal: busca na internet disponível de novo.
    client.put("/api/settings", json={"offline": False})
    client.post("/api/chat", json={"messages": [{"role": "user", "content": "oi"}]})
    names = [t["function"]["name"] for t in upstream.ollama_bodies[-1]["tools"]]
    assert "buscar_web" in names


def test_offline_persists(client, store):
    client.put("/api/settings", json={"offline": True})
    assert store.prefs["offline"] is True


def test_models_list_and_switch(client, upstream, store):
    d = client.get("/api/models").json()
    assert d["installed"][0]["name"] == "qwen3:8b" and d["installed"][0]["role"] == "conversa"
    assert all(s["name"] != "qwen3:8b" for s in d["suggested"])
    # Modelo não instalado: recusa e explica como baixar.
    r = client.put("/api/models/chat", json={"name": "dolphin3:8b"})
    assert r.status_code == 404 and "ollama pull dolphin3:8b" in r.json()["detail"]
    assert client.put("/api/models/chat", json={"name": "qwen3:8b; rm"}).status_code == 422


def test_switch_model_is_used_in_chat(client, upstream, store):
    upstream.ollama_models = ["qwen3:8b", "dolphin3:8b"]
    assert client.put("/api/models/chat", json={"name": "dolphin3:8b"}).json() == {"chat_model": "dolphin3:8b"}
    assert store.prefs["chat_model"] == "dolphin3:8b"
    client.post("/api/chat", json={"messages": [{"role": "user", "content": "oi"}]})
    assert upstream.ollama_bodies[-1]["model"] == "dolphin3:8b"
    assert client.get("/api/desktop/services").json()["chat_model"] == "dolphin3:8b"


def test_unload_and_load(client, upstream):
    assert client.post("/api/models/qwen3:8b/unload").json() == {"ok": True}
    assert upstream.ollama_generate[-1] == {"model": "qwen3:8b", "keep_alive": 0}
    assert client.post("/api/models/qwen3:8b/load").json() == {"ok": True}
    assert client.post("/api/models/naoexiste:1b/load").status_code == 404


def test_logs_tail_and_filter(tmp_path):
    from sexta.desktop import tail
    log = tmp_path / "servidor.log"
    log.write_text("".join(f"linha {i} {'ERROR' if i % 10 == 0 else 'INFO'}\n" for i in range(1000)), encoding="utf-8")
    assert tail(log, 3) == ["linha 997 INFO", "linha 998 INFO", "linha 999 INFO"]
    assert tail(log, 2, "error") == ["linha 980 ERROR", "linha 990 ERROR"]
    assert tail(tmp_path / "nada.log") == []


def test_logs_endpoint(client):
    d = client.get("/api/logs?lines=5").json()
    assert "lines" in d and d["file"].endswith("servidor.log")


def test_panel_can_be_framed_by_desktop(client):
    assert client.get("/api/health").headers["x-frame-options"] == "SAMEORIGIN"


def test_desktop_page_served(client):
    r = client.get("/desktop.html")
    assert r.status_code == 200 and "desktop.js" in r.text


def test_launcher_helpers(tmp_path):
    import sexta_desktop as d
    cmd = d.server_command(tmp_path)
    assert cmd[1:4] == ["-m", "uvicorn", "sexta.app:app"] and "127.0.0.1" in cmd
    assert d.autostart_command(tmp_path).endswith("--bandeja")
    assert d.get_autostart() is False or sys.platform == "win32"


def test_single_instance():
    import sexta_desktop as d
    first = d.claim_single_instance()
    if first is None:
        pytest.skip("porta de trava ocupada nesta máquina")
    try:
        assert d.claim_single_instance() is None   # segunda cópia só avisa a primeira
    finally:
        first.close()
