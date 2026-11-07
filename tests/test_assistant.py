from sexta.assistant import _strip_think, wants_vision


def _ask(client, text, **extra):
    return client.post("/api/chat", json={"messages": [{"role": "user", "content": text}], **extra})


def test_chat_uses_panel_context_in_portuguese(client, upstream):
    r = _ask(client, "Como está o tempo?")
    assert r.status_code == 200
    assert r.json()["text"] == "Olá, Wender."
    body = upstream.ollama_bodies[0]
    assert body["model"] == "qwen3:8b"
    assert body["think"] is False
    system = body["messages"][0]["content"]
    assert "Sexta-feira" in system and "português" in system
    assert "Lowell, MA" in system and "8.4°C" in system and "BTC" in system
    assert "USDT/BRL: R$" in system


def test_chat_runs_web_search_tool_then_answers(client, upstream, search):
    upstream.ollama_replies = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "buscar_web", "arguments": {"consulta": "jogo do Flamengo"}}}]},
        {"role": "assistant", "content": "O Flamengo venceu por 2 a 1."},
    ]
    r = _ask(client, "Quanto foi o jogo do Flamengo?").json()
    assert search.queries == ["jogo do Flamengo"]
    assert r["text"] == "O Flamengo venceu por 2 a 1."
    assert r["sources"][0]["href"] == "https://exemplo.com/jogo"
    tool_msg = upstream.ollama_bodies[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and "Flamengo venceu" in tool_msg["content"]


def test_image_goes_to_vision_model_only_when_asked(client, upstream):
    _ask(client, "O que você vê na câmera?", image="aW1n")
    assert upstream.ollama_bodies[-1]["model"] == "qwen2.5vl:7b"
    assert upstream.ollama_bodies[-1]["messages"][-1]["images"] == ["aW1n"]
    _ask(client, "Conte uma piada", image="aW1n")
    assert upstream.ollama_bodies[-1]["model"] == "qwen3:8b"
    assert "images" not in upstream.ollama_bodies[-1]["messages"][-1]


def test_chat_reports_ollama_offline(client, upstream):
    upstream.fail.add("127.0.0.1")
    r = _ask(client, "Oi")
    assert r.status_code == 503
    assert "Ollama" in r.json()["detail"]


def test_chat_rejects_history_ending_with_assistant(client):
    r = client.post("/api/chat", json={"messages": [{"role": "assistant", "content": "oi"}]})
    assert r.status_code == 400


def test_transcribe(client):
    r = client.post("/api/transcribe", content=b"fake-audio",
                    headers={"content-type": "audio/mp4"})
    assert r.json()["text"] == "qual a temperatura agora"
    assert client.post("/api/transcribe", content=b"").status_code == 400


def test_assistant_status(client):
    st = client.get("/api/assistant/status").json()
    assert st["online"] is True and st["chat_model_ready"] is True
    assert st["vision_model_ready"] is False


def test_system_stats(client):
    s = client.get("/api/system").json()
    assert "cpu" in s and "gpu" in s


def test_helpers():
    assert wants_vision("o que é isso na minha mão?")
    assert wants_vision("Olha isso aqui")
    assert not wants_vision("qual a cotação do dólar")
    assert _strip_think("<think>hmm</think> Oi!") == "Oi!"


def test_news_tool_returns_headlines_with_sources(client, upstream, news, search):
    upstream.ollama_replies = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "buscar_noticias", "arguments": {"consulta": "Brasil"}}}]},
        {"role": "assistant", "content": "Segundo o g1, o Copom manteve os juros."},
    ]
    r = _ask(client, "Quais as principais notícias de hoje?").json()
    assert news.queries == ["Brasil"] and search.queries == []
    assert r["sources"][0]["href"] == "https://g1.globo.com/economia/copom"
    tools = [t["function"]["name"] for t in upstream.ollama_bodies[0]["tools"]]
    assert tools == ["buscar_web", "buscar_noticias"]


def test_tts_returns_wav(client):
    r = client.post("/api/tts", json={"text": "São três horas."})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content.startswith(b"RIFF")
    assert client.post("/api/tts", json={"text": "  "}).status_code == 400


def test_to_wav_header():
    import wave, io
    from sexta.tts import to_wav
    data = to_wav([0.0, 0.5, -0.5], 24000)
    with wave.open(io.BytesIO(data)) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 3
