# Sexta-feira

Assistente pessoal de IA que roda no seu PC 24/7 e usa o iPad como visor.

## O que ela faz

- **Visual de HUD futurista** feito para o iPad deitado: fundo animado (rede de partículas e grade
  em movimento), núcleo com anéis girando que reage à sua voz, números animados e minigráficos.
- **Painel ao vivo**: clima de Lowell, MA com nascer e pôr do sol ([Open-Meteo](https://open-meteo.com/)),
  BTC, ETH, POL, UNI, DOT e LINK em US$ e R$ ([CoinGecko](https://www.coingecko.com/)),
  USDT/BRL com conversor (Binance, com reserva pelo CoinGecko porque a Binance bloqueia IPs dos EUA).
- **Sistema do PC**: uso de CPU, RAM, GPU e VRAM da RTX em tempo real.
- **Conversa com a IA local** (Ollama, `qwen3:8b`), em português, sabendo o clima e as cotações do painel.
- **Busca na internet** quando a pergunta precisa de informação atual (DuckDuckGo, sem chave), com as fontes.
- **Visão**: com a câmera ligada, pergunte "o que você está vendo?" e ela analisa a imagem (`qwen2.5vl:7b`).
- **Voz**: segure **FALAR** para conversar, ou ligue a **ESCUTA** e comece com "Sexta-feira…".
  Ela ouve com o Whisper no PC e responde com a voz do iPad. **MUDO** silencia as respostas.

Veja [docs/voz-e-ia.md](docs/voz-e-ia.md) para instalar a IA e a voz, e
[docs/arquitetura.md](docs/arquitetura.md) para a pesquisa e as escolhas.

## Rodar rápido

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # opcional: ajuste cidade, moedas e chave do CoinGecko
uvicorn sexta.app:app --app-dir server --host 127.0.0.1 --port 8000
```

Abra http://localhost:8000 no PC. Para usar no iPad com câmera e microfone, siga
[docs/instalacao-windows.md](docs/instalacao-windows.md): o Safari só libera câmera e
microfone em HTTPS, e o Tailscale resolve isso.

## API

| Rota | O que devolve | Atualização |
| --- | --- | --- |
| `GET /api/weather` | Clima atual e 3 dias | 1 h (2 h de madrugada) |
| `GET /api/crypto` | Preços das moedas configuradas | 30 min (1 h de madrugada) |
| `GET /api/usdtbrl` | Cotação USDT/BRL | 30 min (1 h de madrugada) |
| `POST /api/chat` | Resposta da IA (`{messages, image?}`) | — |
| `POST /api/transcribe` | Texto do áudio enviado (corpo = áudio) | — |
| `GET /api/assistant/status` | Ollama online, modelos prontos, Whisper instalado | — |
| `GET /api/system` | CPU, RAM, GPU e VRAM do PC | a cada 1 min no painel (5 min de madrugada) |
| `GET /api/config` | Cidade, moedas e intervalos | — |
| `GET /api/health` | `{"status": "ok"}` | — |

As respostas ficam em cache no servidor, então vários aparelhos abertos não gastam
mais chamadas. Se uma API cair, o painel mostra o último valor por até 10 vezes o
intervalo normal.

## Configuração (`.env`)

Veja [.env.example](.env.example). Para trocar as moedas, use
`SEXTA_COINS=BTC:bitcoin,ETH:ethereum,...` com o id de cada moeda no CoinGecko.
A chave gratuita do plano Demo do CoinGecko (`COINGECKO_API_KEY`) é opcional, mas
evita bloqueios; o plano dá 10 mil chamadas por mês, e o intervalo de 30 min usa cerca de 1.500.

## Testes

```bash
pip install -r requirements-dev.txt
pytest          # servidor: APIs simuladas, sem internet
npm test        # formatação do painel (Node 20+)
```

## Estrutura

```
server/sexta/   servidor FastAPI (config, cache, fontes de dados, IA, voz, sistema)
web/            app do iPad (HTML, CSS, JS, service worker, manifest)
tests/          testes do servidor
web/tests/      testes do front-end
scripts/        iniciar.ps1 para o Windows
docs/           arquitetura e instalação
```
