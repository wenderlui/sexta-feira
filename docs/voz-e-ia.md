# Voz e IA local

Tudo roda no seu PC (RTX 4070 Ti, 12 GB). Nada de áudio ou imagem vai para a nuvem,
exceto as buscas na internet, que vão para o DuckDuckGo.

## Como funciona

```
iPad: segura FALAR ──áudio──▶ PC: Whisper (ouvir) ──texto──▶ Ollama qwen3:8b (pensar)
                                                       │  └─ precisa de dado atual? busca na web
                                                       │  └─ câmera ligada + "o que você vê"? qwen2.5vl:7b
iPad: fala a resposta ◀──────────texto───────────────────┘
```

- **Ouvir**: `faster-whisper` com o modelo `large-v3-turbo` na GPU. Sem GPU, cai para a CPU sozinho.
  Se o Whisper não estiver instalado, o botão FALAR usa o reconhecimento de voz do próprio Safari.
- **Pensar**: Ollama com `qwen3:8b` (modo sem "pensamento" para responder rápido).
  A IA recebe junto o clima, as cotações e a hora, então responde sobre eles sem buscar.
- **Falar**: a voz em português do próprio iPad (Ajustes > Acessibilidade > Conteúdo Falado > Vozes
  permite baixar uma voz "aprimorada" mais natural, como a Luciana).

## Instalar no PC

```powershell
winget install -e --id Ollama.Ollama
ollama pull qwen3:8b
ollama pull qwen2.5vl:7b
cd "C:\Users\wende\OneDrive\Documentos\sexta feira"
.\.venv\Scripts\python.exe -m pip install -r requirements-voz.txt
```

O `scripts\iniciar.ps1` já instala o `requirements-voz.txt` sozinho a cada início.

## Usar

| Botão | O que faz |
| --- | --- |
| **FALAR** (segurar) | Grava enquanto você segura; ao soltar, ela responde |
| **ESCUTA** | Microfone sempre ligado. Comece com "Sexta-feira, …". Por 10 s depois de cada resposta, não precisa repetir o nome |
| **CÂMERA** | Mostra a câmera dentro do núcleo. Pergunte "o que você está vendo?", "leia isso", "o que tenho na mão?" |
| **MUDO** | Ela responde só por escrito |
| Caixa de texto | Escreva a pergunta, se preferir |

Os três selos no topo mostram o estado: **LINK** (painel), **IA** (Ollama e modelo) e **VOZ** (Whisper).
Verde = pronto, amarelo = parcial, vermelho = fora do ar.

## Trocar de modelo

No `.env`: `SEXTA_CHAT_MODEL`, `SEXTA_VISION_MODEL` e `SEXTA_WHISPER_MODEL`.
Para respostas mais rápidas, `qwen3:4b`; para entender melhor fala com ruído, `large-v3`.

## Limites conhecidos

- O iOS desliga câmera e microfone se a tela bloquear ou o app sair da frente.
- A ESCUTA usa um detector de volume simples; em ambiente barulhento, prefira FALAR.
- A busca usa o DuckDuckGo sem chave, que pode limitar muitas buscas seguidas.
