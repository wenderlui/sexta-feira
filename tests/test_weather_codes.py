from sexta.config import DEFAULT_COINS, _parse_coins
from sexta.providers import describe_weather


def test_describe_known_and_unknown_codes():
    assert describe_weather(0)[0] == "Céu limpo"
    assert describe_weather(95)[0] == "Trovoada"
    assert describe_weather(1234)[0] == "Desconhecido"
    assert describe_weather(None)[0] == "Sem dados"


def test_parse_coins():
    assert _parse_coins("btc:bitcoin, eth:ethereum") == {"BTC": "bitcoin", "ETH": "ethereum"}
    assert _parse_coins("") == DEFAULT_COINS
