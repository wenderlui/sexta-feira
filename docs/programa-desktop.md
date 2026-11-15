# Programa do PC (Sexta-feira para Windows)

Uma janela própria da Sexta-feira no PC, com menus, que fica aberta 24/7 na bandeja do
Windows (perto do relógio). A IA roda **toda no PC**: Ollama na RTX 4070 Ti, Whisper para
ouvir e Kokoro para falar. Nenhum dado vai para a nuvem.

## Instalar

1. Atualize a pasta do projeto (`git pull`).
2. Botão direito em `scripts\instalar-desktop.ps1` > **Executar com o PowerShell**.
   Ele instala `pywebview`, `pystray` e `pillow` no `.venv` e cria o atalho
   **Sexta-feira** na Área de Trabalho e no Menu Iniciar.
3. Abra pelo atalho. Em **Ajustes**, marque **Abrir com o Windows** para ela já começar
   escondida na bandeja quando o PC ligar.

A janela usa o Edge WebView2, que já vem no Windows 11.

## Como funciona

- Se o servidor (Tarefa Agendada) já estiver rodando, a janela só se conecta a ele.
  Se não estiver, o programa sobe o servidor sozinho (`logs\servidor.log`).
- Se o Ollama estiver fechado, o programa o abre.
- Fechar a janela (X ou Esc) **esconde** a Sexta-feira na bandeja. Para sair de vez:
  botão direito no ícone da bandeja > **Sair**.
- Abrir o atalho de novo só traz a janela para a frente (nunca abre duas).

## Menus

| Tela | O que faz |
|------|-----------|
| **Início** (Ctrl+1) | CPU, RAM, GPU, VRAM, tempo ligado, estado de cada serviço, pergunta rápida e alertas das câmeras |
| **Conversa** (Ctrl+2) | Chat com a IA (histórico salvo no PC), microfone (Ctrl+Espaço), "Falar respostas", copiar e ouvir cada resposta, fontes das pesquisas |
| **Painel HUD** (Ctrl+3) | O mesmo painel do iPad, dentro da janela |
| **Modelos** (Ctrl+4) | Modelos instalados no Ollama, quanto ocupam, quais estão na GPU; **Usar na conversa**, **Carregar** e **Liberar GPU**; sugestões para a placa de 12 GB |
| **Serviços** (Ctrl+5) | Servidor, Ollama, Whisper, voz, internet, Home Assistant e Tailscale; **Reiniciar servidor** |
| **Registros** (Ctrl+6) | `logs\servidor.log` ao vivo, com filtro e cores (erro, aviso, iPad) |
| **Ajustes** (Ctrl+7) | Abrir com o Windows, pastas, voz (motor, voz, velocidade, testar) |

**Modo offline** (no menu lateral): a IA não pesquisa na internet e a voz passa a ser só o
Kokoro. Fica salvo em `data\ajustes.json` e vale também para o iPad.

Menu da bandeja: Abrir, Painel no navegador, Reiniciar servidor, Abrir com o Windows, Sair.

## Escolher o modelo (o "cérebro")

Em **Modelos**, qualquer modelo instalado no Ollama pode virar o da conversa. A escolha fica
salva no PC. Para instalar um novo, abra o terminal e rode, por exemplo:

```
ollama pull dolphin3:8b
```

O jeito de responder depende do modelo. Os ajustados para obedecer o dono, como o
`dolphin3`, recusam bem menos que os modelos padrão. Modelos até ~14B cabem nos 12 GB da
RTX 4070 Ti; o `qwen3:8b` continua sendo o mais rápido e o melhor para usar ferramentas.

## API nova (só no PC)

| Rota | Uso |
|------|-----|
| `GET /api/desktop/services` | estado de cada serviço + telemetria do PC |
| `GET /api/models` | modelos instalados, na GPU e sugeridos |
| `PUT /api/models/chat` `{"name": "dolphin3:8b"}` | troca o modelo da conversa |
| `POST /api/models/{nome}/load` / `unload` | sobe ou tira o modelo da GPU |
| `GET /api/logs?lines=200&q=erro` | fim do registro, com filtro |
| `PUT /api/settings` `{"offline": true}` | liga/desliga o modo offline |

## Próximas etapas

- **Etapa 2: modo agente (autonomia).** A Sexta-feira passa a agir sozinha em vários passos
  com ferramentas no PC: abrir programas e sites, ler e organizar arquivos, rodar comandos,
  controlar a casa, pesquisar e resumir. Tudo registrado num diário de ações. Ações
  arriscadas (apagar, gastar dinheiro, enviar mensagem em seu nome) pedem confirmação na
  janela; em Ajustes você escolhe o que ela pode fazer sem perguntar.
- **Etapa 3: memória e rotinas.** Memória de longo prazo local (o que ela aprende sobre você),
  lembretes e rotinas agendadas (resumo da manhã, contas a vencer do Gmail), notificações do
  Windows.
- **Etapa 4: olhos e atalhos.** Palavra "Sexta-feira" também no microfone do PC, atalho
  global (ex.: Win+Shift+S) que abre a conversa por cima de tudo, visão da tela e da webcam,
  instalador `.exe` (PyInstaller) e baixar modelos pelo próprio programa.
