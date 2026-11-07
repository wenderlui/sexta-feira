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
| **OUVINDO / MUDO** | Ao abrir, ela já fica ouvindo (verde). Comece com "Sexta-feira, …". Por 10 s depois de cada resposta, não precisa repetir o nome. Toque para MUDO (âmbar): o microfone desliga. A escolha fica salva no iPad |
| **FALAR** (segurar) | Grava enquanto você segura, mesmo no MUDO; ao soltar, ela responde. Bom em lugar barulhento |
| **CÂMERA** | Mostra a câmera dentro do núcleo e volta como você deixou. Pergunte "o que você está vendo?", "leia isso", "o que tenho na mão?" |
| **SEM VOZ** | Ela responde só por escrito |
| Caixa de texto | Escreva a pergunta, se preferir |

Os três selos no topo mostram o estado: **LINK** (painel), **IA** (Ollama e modelo) e **VOZ** (Whisper).
Verde = pronto, amarelo = parcial, vermelho = fora do ar.

## Buscas e velocidade

- A busca prefere resultados em português, lê o começo das 3 primeiras páginas (não só o resumo)
  e guarda o resultado por 10 minutos, então repetir a pergunta é instantâneo.
- Quando o servidor liga, ele já carrega o `qwen3:8b` e o Whisper na GPU, e o modelo de conversa
  fica carregado para sempre (`keep_alive: -1`). O de visão sai da memória 10 min depois do uso.

## Trocar de modelo

No `.env`: `SEXTA_CHAT_MODEL`, `SEXTA_VISION_MODEL` e `SEXTA_WHISPER_MODEL`.
Para respostas mais rápidas, `qwen3:4b`; para entender melhor fala com ruído, `large-v3`.

## Limites conhecidos

- O iOS desliga câmera e microfone se a tela bloquear ou o app sair da frente.
- A escuta usa um detector de volume simples; em ambiente barulhento, prefira FALAR.
- No iOS, o microfone só começa a medir o volume depois do primeiro toque na tela.
- Placar de futebol não é confiável com a busca atual (ficou para depois).
- A busca usa o DuckDuckGo sem chave, que pode limitar muitas buscas seguidas.

## Voz da Sexta-feira (Kokoro no PC)

No iPad, a voz do próprio Safari fica muda enquanto o microfone está gravando. Por isso a
resposta falada é gerada no PC com o [Kokoro](https://github.com/thewh1teagle/kokoro-onnx)
(local e gratuito, voz feminina `pf_dora`) pelo `POST /api/tts`, e o iPad toca o WAV pelo
mesmo áudio do microfone. Na primeira vez o servidor baixa os modelos (~330 MB) para `models/`.
Se o Kokoro não estiver instalado, o iPad volta para a voz do Safari.

Configuração opcional no `.env`: `SEXTA_TTS_VOICE` (ex.: `pm_alex` para voz masculina) e
`SEXTA_TTS_SPEED` (padrão 1.05).
