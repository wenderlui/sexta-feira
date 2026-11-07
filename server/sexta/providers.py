"""Fontes de dados do painel: Open-Meteo (clima), CoinGecko (cripto), Binance (USDT/BRL)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from .config import Settings

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
BINANCE_URL = "https://api.binance.com/api/v3/ticker/price"

# Códigos de tempo da OMM usados pelo Open-Meteo -> (descrição, ícone)
WEATHER_CODES: dict[int, tuple[str, str]] = {
    0: ("Céu limpo", "☀️"),
    1: ("Quase limpo", "🌤️"),
    2: ("Parcialmente nublado", "⛅"),
    3: ("Nublado", "☁️"),
    45: ("Neblina", "🌫️"),
    48: ("Neblina com geada", "🌫️"),
    51: ("Garoa fraca", "🌦️"),
    53: ("Garoa", "🌦️"),
    55: ("Garoa forte", "🌧️"),
    56: ("Garoa congelante", "🌧️"),
    57: ("Garoa congelante forte", "🌧️"),
    61: ("Chuva fraca", "🌦️"),
    63: ("Chuva", "🌧️"),
    65: ("Chuva forte", "🌧️"),
    66: ("Chuva congelante", "🌧️"),
    67: ("Chuva congelante forte", "🌧️"),
    71: ("Neve fraca", "🌨️"),
    73: ("Neve", "🌨️"),
    75: ("Neve forte", "❄️"),
    77: ("Grãos de neve", "🌨️"),
    80: ("Pancadas de chuva", "🌦️"),
    81: ("Pancadas de chuva fortes", "🌧️"),
    82: ("Pancadas violentas", "⛈️"),
    85: ("Pancadas de neve", "🌨️"),
    86: ("Pancadas de neve fortes", "❄️"),
    95: ("Trovoada", "⛈️"),
    96: ("Trovoada com granizo", "⛈️"),
    99: ("Trovoada com granizo forte", "⛈️"),
}


def describe_weather(code: int | None) -> tuple[str, str]:
    if code is None:
        return ("Sem dados", "❔")
    return WEATHER_CODES.get(int(code), ("Desconhecido", "❔"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def fetch_weather(client: httpx.AsyncClient, s: Settings) -> dict[str, Any]:
    params = {
        "latitude": s.latitude,
        "longitude": s.longitude,
        "timezone": s.timezone,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
        "weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max",
        "forecast_days": 3,
    }
    r = await client.get(OPEN_METEO_URL, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    cur = data.get("current", {})
    desc, icon = describe_weather(cur.get("weather_code"))
    daily = data.get("daily", {})
    days = []
    for i, day in enumerate(daily.get("time", [])):
        d_desc, d_icon = describe_weather(_at(daily.get("weather_code"), i))
        days.append(
            {
                "date": day,
                "max": _at(daily.get("temperature_2m_max"), i),
                "min": _at(daily.get("temperature_2m_min"), i),
                "rain_chance": _at(daily.get("precipitation_probability_max"), i),
                "description": d_desc,
                "icon": d_icon,
            }
        )
    return {
        "city": s.city_name,
        "temperature": cur.get("temperature_2m"),
        "feels_like": cur.get("apparent_temperature"),
        "humidity": cur.get("relative_humidity_2m"),
        "wind_kmh": cur.get("wind_speed_10m"),
        "description": desc,
        "icon": icon,
        "days": days,
        "source": "Open-Meteo",
        "updated_at": _now_iso(),
    }


def _at(values: list | None, i: int):
    if not values or i >= len(values):
        return None
    return values[i]


def _coingecko_headers(s: Settings) -> dict[str, str]:
    return {"x-cg-demo-api-key": s.coingecko_api_key} if s.coingecko_api_key else {}


async def fetch_crypto(client: httpx.AsyncClient, s: Settings) -> dict[str, Any]:
    # O Tether entra sempre na mesma chamada: serve de reserva para o USDT/BRL
    # sem gastar outra chamada do limite mensal do CoinGecko.
    ids = ",".join(dict.fromkeys([*s.coins.values(), "tether"]))
    params = {
        "ids": ids,
        "vs_currencies": "usd,brl",
        "include_24hr_change": "true",
    }
    r = await client.get(
        COINGECKO_URL, params=params, headers=_coingecko_headers(s), timeout=10
    )
    r.raise_for_status()
    data = r.json()
    coins = []
    for symbol, cg_id in s.coins.items():
        row = data.get(cg_id)
        if not row:
            continue
        coins.append(
            {
                "symbol": symbol,
                "id": cg_id,
                "usd": row.get("usd"),
                "brl": row.get("brl"),
                "change_24h": row.get("usd_24h_change"),
            }
        )
    tether = data.get("tether") or {}
    return {
        "coins": coins,
        "usdt_brl": tether.get("brl"),
        "usdt_brl_change_24h": tether.get("brl_24h_change"),
        "source": "CoinGecko",
        "updated_at": _now_iso(),
    }


async def fetch_binance_usdtbrl(client: httpx.AsyncClient) -> dict[str, Any]:
    """USDT/BRL em tempo real pela Binance.

    A api.binance.com bloqueia IPs dos EUA (responde 451), então nos EUA o
    painel usa a reserva do CoinGecko automaticamente.
    """
    r = await client.get(BINANCE_URL, params={"symbol": "USDTBRL"}, timeout=10)
    r.raise_for_status()
    return {
        "pair": "USDT/BRL",
        "price": float(r.json()["price"]),
        "source": "Binance",
        "updated_at": _now_iso(),
    }


def usdtbrl_from_crypto(crypto: dict[str, Any]) -> dict[str, Any]:
    price = crypto.get("usdt_brl")
    if price is None:
        raise KeyError("tether")
    return {
        "pair": "USDT/BRL",
        "price": float(price),
        "change_24h": crypto.get("usdt_brl_change_24h"),
        "source": "CoinGecko",
        "updated_at": crypto.get("updated_at"),
    }
