"""Cache em memória com tempo de vida, para respeitar os limites das APIs gratuitas."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable


class TTLCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._data: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_or_fetch(
        self, key: str, ttl: float, fetch: Callable[[], Awaitable[Any]]
    ) -> tuple[Any, bool]:
        """Devolve (valor, veio_do_cache).

        Se a busca falhar e houver um valor de até 10 vezes o ttl, devolve esse
        valor antigo em vez de quebrar o painel. Senão, a exceção sobe.
        """
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = self._clock()
            cached = self._data.get(key)
            if cached and now - cached[0] < ttl:
                return cached[1], True
            try:
                value = await fetch()
            except Exception:
                if cached and now - cached[0] < ttl * 10:
                    return cached[1], True
                raise
            self._data[key] = (now, value)
            return value, False
