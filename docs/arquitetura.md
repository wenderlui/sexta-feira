# Arquitetura

O documento completo, com o comparativo de projetos open source, o que dizem os
fóruns e as fontes, está em:
https://claude.ai/artifact/1ZcPCHSebx5iHTGspUJCzt

## Resumo

- **PC 24/7 (cérebro)**: i7-13700F, 32 GB de RAM, RTX 4070 Ti (12 GB de VRAM).
- **iPad (visor)**: app web instalado na tela de início, falando com o PC pelo Tailscale (HTTPS).
- **Painel** (esta parte): FastAPI + Open-Meteo + CoinGecko + Binance, com cache no servidor.
- **Voz e visão** (parte 2): Pipecat orquestrando faster-whisper (ouvir), Ollama (pensar e ver)
  e Kokoro (falar), transporte WebRTC direto do navegador.
- **Busca** (parte 2): SearXNG em Docker.
- **Integrações** (etapas 3 e 4): Gmail, redes sociais e banco, sempre só leitura.

## Modelos sugeridos para a RTX 4070 Ti (12 GB)

| Uso | Modelo | Observação |
| --- | --- | --- |
| Conversa | qwen3:8b (Q4) | Cabe com folga junto do Whisper |
| Visão | qwen2.5vl:7b | Carregado só quando a câmera é usada |
| Ouvir | faster-whisper `medium` ou `large-v3-turbo` | Entende bem português |
| Falar | Kokoro | Roda na GPU ou CPU |

Esses tamanhos serão medidos no seu PC na parte 2.
