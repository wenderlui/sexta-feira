"""Modo espera: nada fica na placa de vídeo à toa; tudo sobe quando alguém fala."""
import time

from sexta.config import Settings
from sexta.speech import Transcriber


def test_nothing_is_loaded_when_the_server_starts(client, upstream):
    assert upstream.ollama_generate == []
    status = client.get("/api/assistant/status").json()
    assert status["loaded"] == {"chat": False, "whisper": False}


def test_wake_loads_chat_with_idle_timeout(client, upstream):
    assert client.post("/api/wake").json()["waking"] is True
    body = upstream.ollama_generate[-1]
    assert body["model"] == "qwen3:8b" and body["keep_alive"] == "10m"
    assert body["options"]["num_ctx"] == 8192
    # Pedidos seguidos (várias falas) não recarregam de novo.
    assert client.post("/api/wake").json()["waking"] is False
    assert len(upstream.ollama_generate) == 1


def test_status_reports_what_is_loaded(client, upstream):
    upstream.ollama_loaded = ["qwen3:8b"]
    assert client.get("/api/assistant/status").json()["loaded"]["chat"] is True


def test_chat_and_vision_leave_the_gpu_when_idle(client, upstream):
    client.post("/api/chat", json={"messages": [{"role": "user", "content": "oi"}]})
    assert upstream.ollama_bodies[-1]["keep_alive"] == "10m"
    upstream.ollama_replies.append({"role": "assistant", "content": "Vejo uma caneca."})
    client.post("/api/chat", json={"messages": [{"role": "user", "content": "o que você vê na câmera?"}],
                                   "image": "aGVsbG8="})
    assert upstream.ollama_bodies[-1]["model"] == "qwen2.5vl:7b"
    assert upstream.ollama_bodies[-1]["keep_alive"] == "1m"


def test_whisper_unloads_only_after_idle_time():
    ears = Transcriber(Settings())
    ears._model = object()
    ears.last_used = time.time()
    assert ears.unload_if_idle(600) is False and ears.loaded
    ears.last_used = time.time() - 601
    assert ears.unload_if_idle(600) is True and not ears.loaded
