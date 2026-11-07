"""Deixa as buscas melhores: prefere português, lê o começo das páginas e guarda em cache."""

from __future__ import annotations

import asyncio
import html
import re
import time
from typing import Any, Awaitable, Callable

import httpx

PT = re.compile(r"\b(não|são|também|está|você|isso|pelo|pela|mais|para|como|uma|então|já|até)\b|ção\b|ções\b|ões\b", re.I)
ES = re.compile(r"\b(el|los|las|del|también|está|pero|muy|año|según|después|viernes|sábado)\b|ñ", re.I)
EN = re.compile(r"\b(the|and|with|from|this|that|after|before|will|have|has|were)\b", re.I)


def language_score(text: str) -> dict[str, int]:
    return {"pt": len(PT.findall(text)), "es": len(ES.findall(text)), "en": len(EN.findall(text))}


def is_portuguese(text: str) -> bool:
    s = language_score(text)
    return s["pt"] >= max(s["es"], s["en"]) and s["pt"] > 0


def prefer_portuguese(rows: list[dict[str, Any]], minimum: int = 3) -> list[dict[str, Any]]:
    """Coloca os resultados em português primeiro; descarta os outros se sobrarem pelo menos `minimum`."""
    pt = [r for r in rows if is_portuguese(f"{r.get('title', '')} {r.get('body', '')}")]
    if len(pt) >= minimum:
        return pt
    rest = [r for r in rows if r not in pt]
    return pt + rest


_TAGS = re.compile(r"<(script|style|noscript|svg|header|footer|nav|form)[^>]*>.*?</\1>", re.S | re.I)
_ANY_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def page_text(raw_html: str, limit: int = 1500) -> str:
    """Texto visível aproximado de uma página (sem dependências extras)."""
    body = raw_html
    m = re.search(r"<(article|main)[^>]*>(.*?)</\1>", raw_html, re.S | re.I)
    if m:
        body = m.group(2)
    text = _ANY_TAG.sub(" ", _TAGS.sub(" ", body))
    text = _SPACES.sub(" ", html.unescape(text)).strip()
    return text[:limit]


class Research:
    """Envolve as funções de busca com cache, preferência por português e leitura das páginas."""

    def __init__(self, client: httpx.AsyncClient, ttl: float = 600, read_pages: int = 3,
                 page_timeout: float = 4.0, clock: Callable[[], float] = time.monotonic):
        self.client = client
        self.ttl = ttl
        self.read_pages = read_pages
        self.page_timeout = page_timeout
        self.clock = clock
        self._cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}

    async def _read(self, row: dict[str, Any]) -> None:
        url = row.get("href") or ""
        if not url.startswith("http"):
            return
        try:
            r = await self.client.get(
                url, timeout=self.page_timeout, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (sexta-feira)", "Accept-Language": "pt-BR,pt;q=0.9"},
            )
            if r.status_code == 200 and "html" in r.headers.get("content-type", ""):
                text = page_text(r.text)
                if len(text) > 200:
                    row["page"] = text
        except (httpx.HTTPError, ValueError):
            pass

    async def run(self, kind: str, query: str,
                  search: Callable[[str], Awaitable[list[dict[str, Any]]]]) -> list[dict[str, Any]]:
        key = (kind, query.strip().lower())
        now = self.clock()
        hit = self._cache.get(key)
        if hit and now - hit[0] < self.ttl:
            return hit[1]
        rows = prefer_portuguese(await search(query))
        rows = [dict(r) for r in rows[:6]]
        await asyncio.gather(*(self._read(r) for r in rows[: self.read_pages]))
        if any(r.get("href") for r in rows):
            self._cache[key] = (now, rows)
        return rows
