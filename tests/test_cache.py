import asyncio

import pytest

from sexta.cache import TTLCache


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def run(coro):
    return asyncio.run(coro)


def test_cache_expires_after_ttl():
    clock = Clock()
    cache = TTLCache(clock)
    n = {"calls": 0}

    async def fetch():
        n["calls"] += 1
        return n["calls"]

    assert run(cache.get_or_fetch("k", 10, fetch)) == (1, False)
    clock.t = 5
    assert run(cache.get_or_fetch("k", 10, fetch)) == (1, True)
    clock.t = 11
    assert run(cache.get_or_fetch("k", 10, fetch)) == (2, False)


def test_stale_value_is_used_when_fetch_fails_but_not_forever():
    clock = Clock()
    cache = TTLCache(clock)

    async def ok():
        return "bom"

    async def boom():
        raise RuntimeError("fora do ar")

    run(cache.get_or_fetch("k", 10, ok))
    clock.t = 50
    assert run(cache.get_or_fetch("k", 10, boom)) == ("bom", True)
    clock.t = 101
    with pytest.raises(RuntimeError):
        run(cache.get_or_fetch("k", 10, boom))
