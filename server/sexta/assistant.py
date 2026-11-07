"""Cérebro da Sexta-feira: conversa com o Ollama, com busca na web e visão."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .config import Settings

SYSTEM_PROMPT = """Você é a Sexta-feira, a assistente pessoal de IA do Wender.
Fale sempre em português do Brasil, de forma natural, curta e direta, como numa conversa falada:
no máximo 3 frases, a não ser que ele peça detalhes. Não use markdown, listas, emojis nem tabelas,
porque sua resposta será lida em voz alta. Escreva números e valores de um jeito fácil de falar.
Você roda localmente no computador dele e aparece num iPad que funciona como visor.
Quando precisar de informação atual (notícias, resultados, preços que não estão abaixo,
qualquer fato recente), use a ferramenta buscar_web antes de responder e cite a fonte em poucas palavras.
Nunca invente dados. Se não souber, diga que não sabe.
Ações fora do computador (pagar, enviar mensagem, comprar) você nunca faz sozinha: só sugere."""

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "buscar_web",
        "description": "Pesquisa na internet e devolve os principais resultados (título, trecho, link).",
        "parameters": {
            "type": "object",
            "properties": {
                "consulta": {"type": "string", "description": "O que pesquisar, em poucas palavras."}
            },
            "required": ["consulta"],
        },
    },
}

VISION_WORDS = re.compile(
    r"\b(v[eê]|veja|vendo|olh[ae]|olhando|enxerga|c[aâ]mera|imagem|foto|isso aqui|"
    r"o que [eé] isso|na minha m[aã]o|minha frente|estou segurando|leia isso|descreva)\b",
    re.IGNORECASE,
)


def wants_vision(text: str) -> bool:
    return bool(VISION_WORDS.search(text or ""))


def _strip_think(text: str) -> str:
    """Remove blocos <think>…</think> que alguns modelos devolvem."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()


def build_context(s: Settings, panel: dict[str, Any]) -> str:
    now = datetime.now(ZoneInfo(s.timezone))
    lines = [f"Agora são {now:%H:%M} de {now:%d/%m/%Y} ({s.timezone}), em {s.city_name}."]
    w = panel.get("weather")
    if w:
        lines.append(
            f"Clima agora: {w.get('temperature')}°C, {w.get('description')}, "
            f"sensação {w.get('feels_like')}°C."
        )
        for d in w.get("days", [])[:3]:
            lines.append(
                f"Previsão {d['date']}: {d.get('description')}, máx {d.get('max')}°C, "
                f"mín {d.get('min')}°C, chuva {d.get('rain_chance')}%."
            )
    c = panel.get("crypto")
    if c:
        prices = ", ".join(
            f"{x['symbol']} US$ {x['usd']} (R$ {x['brl']}, {round(x['change_24h'] or 0, 2)}% em 24h)"
            for x in c.get("coins", [])
        )
        lines.append(f"Cripto: {prices}.")
    u = panel.get("usdtbrl")
    if u:
        lines.append(f"USDT/BRL: R$ {u.get('price')} (fonte {u.get('source')}).")
    return "Dados do painel (já atualizados, use sem buscar):\n" + "\n".join(lines)


async def web_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Busca pelo DuckDuckGo (pacote ddgs), sem chave e sem custo."""
    try:
        from ddgs import DDGS
    except ImportError:  # pragma: no cover - dependência opcional
        return [{"title": "Busca indisponível", "body": "Instale o pacote ddgs.", "href": ""}]

    def _run():
        with DDGS() as d:
            return list(d.text(query, region="br-pt", max_results=max_results))

    try:
        rows = await asyncio.to_thread(_run)
    except Exception as exc:  # rede, bloqueio etc.
        return [{"title": "Falha na busca", "body": str(exc), "href": ""}]
    return [
        {"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")}
        for r in rows
    ]


class Assistant:
    def __init__(self, client: httpx.AsyncClient, settings: Settings, search=web_search):
        self.client = client
        self.s = settings
        self.search = search

    async def _ollama_chat(self, model: str, messages: list[dict], tools=None) -> dict:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.6, "num_ctx": 8192},
        }
        if model.startswith("qwen3"):
            body["think"] = False
        if tools:
            body["tools"] = tools
        r = await self.client.post(f"{self.s.ollama_url}/api/chat", json=body, timeout=180)
        r.raise_for_status()
        return r.json()["message"]

    async def reply(
        self,
        history: list[dict[str, str]],
        panel: dict[str, Any],
        image_b64: str | None = None,
    ) -> dict[str, Any]:
        """history: [{role: user|assistant, content: str}], a última é a pergunta."""
        history = [
            {"role": m["role"], "content": str(m.get("content", ""))[:4000]}
            for m in history[-12:]
            if m.get("role") in ("user", "assistant")
        ]
        if not history or history[-1]["role"] != "user":
            raise ValueError("A última mensagem precisa ser do usuário.")

        system = {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + build_context(self.s, panel)}
        sources: list[dict[str, str]] = []

        if image_b64:
            # Visão: o modelo de visão responde direto sobre a imagem.
            msgs = [system, *history]
            msgs[-1] = {**msgs[-1], "images": [image_b64]}
            msg = await self._ollama_chat(self.s.vision_model, msgs)
            return {"text": _strip_think(msg.get("content", "")), "model": self.s.vision_model,
                    "used_vision": True, "sources": sources}

        msgs: list[dict[str, Any]] = [system, *history]
        for _ in range(3):  # até 3 rodadas de ferramenta
            msg = await self._ollama_chat(self.s.chat_model, msgs, tools=[SEARCH_TOOL])
            calls = msg.get("tool_calls") or []
            if not calls:
                return {"text": _strip_think(msg.get("content", "")), "model": self.s.chat_model,
                        "used_vision": False, "sources": sources}
            msgs.append(msg)
            for call in calls:
                fn = call.get("function", {})
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"consulta": args}
                if fn.get("name") == "buscar_web":
                    results = await self.search(args.get("consulta", ""))
                    sources.extend(r for r in results if r.get("href"))
                    content = json.dumps(results, ensure_ascii=False)[:6000]
                else:
                    content = "Ferramenta desconhecida."
                msgs.append({"role": "tool", "content": content, "tool_name": fn.get("name", "")})
        # Rodadas esgotadas: pede a resposta final sem ferramentas.
        msg = await self._ollama_chat(self.s.chat_model, msgs)
        return {"text": _strip_think(msg.get("content", "")), "model": self.s.chat_model,
                "used_vision": False, "sources": sources}

    async def status(self) -> dict[str, Any]:
        try:
            r = await self.client.get(f"{self.s.ollama_url}/api/tags", timeout=5)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            return {"online": True, "models": models,
                    "chat_model_ready": any(m.startswith(self.s.chat_model) for m in models),
                    "vision_model_ready": any(m.startswith(self.s.vision_model) for m in models)}
        except (httpx.HTTPError, KeyError, ValueError):
            return {"online": False, "models": [], "chat_model_ready": False,
                    "vision_model_ready": False}
