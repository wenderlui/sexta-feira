"""Configuração lida de variáveis de ambiente (arquivo .env opcional)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Carrega um .env simples (CHAVE=valor) sem sobrescrever o ambiente."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Moedas do painel: símbolo exibido -> id no CoinGecko
DEFAULT_COINS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "POL": "polygon-ecosystem-token",
    "UNI": "uniswap",
    "DOT": "polkadot",
    "LINK": "chainlink",
}


def _parse_coins(raw: str | None) -> dict[str, str]:
    """Formato: "BTC:bitcoin,ETH:ethereum"."""
    if not raw:
        return dict(DEFAULT_COINS)
    coins: dict[str, str] = {}
    for item in raw.split(","):
        if ":" in item:
            symbol, cg_id = item.split(":", 1)
            coins[symbol.strip().upper()] = cg_id.strip()
    return coins or dict(DEFAULT_COINS)


@dataclass
class Settings:
    city_name: str = "Lowell, MA"
    latitude: float = 42.6334
    longitude: float = -71.3162
    timezone: str = "America/New_York"
    coins: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_COINS))
    coingecko_api_key: str | None = None
    weather_ttl: int = 600
    crypto_ttl: int = 300
    usdtbrl_ttl: int = 60
    ollama_url: str = "http://127.0.0.1:11434"
    chat_model: str = "qwen3:8b"
    vision_model: str = "qwen2.5vl:7b"
    whisper_model: str = "large-v3-turbo"

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        _load_dotenv(env_file or Path.cwd() / ".env")
        env = os.environ
        return cls(
            city_name=env.get("SEXTA_CITY_NAME", cls.city_name),
            latitude=float(env.get("SEXTA_LATITUDE", cls.latitude)),
            longitude=float(env.get("SEXTA_LONGITUDE", cls.longitude)),
            timezone=env.get("SEXTA_TIMEZONE", cls.timezone),
            coins=_parse_coins(env.get("SEXTA_COINS")),
            coingecko_api_key=env.get("COINGECKO_API_KEY") or None,
            weather_ttl=int(env.get("SEXTA_WEATHER_TTL", cls.weather_ttl)),
            crypto_ttl=int(env.get("SEXTA_CRYPTO_TTL", cls.crypto_ttl)),
            usdtbrl_ttl=int(env.get("SEXTA_USDTBRL_TTL", cls.usdtbrl_ttl)),
            ollama_url=env.get("OLLAMA_URL", cls.ollama_url).rstrip("/"),
            chat_model=env.get("SEXTA_CHAT_MODEL", cls.chat_model),
            vision_model=env.get("SEXTA_VISION_MODEL", cls.vision_model),
            whisper_model=env.get("SEXTA_WHISPER_MODEL", cls.whisper_model),
        )
