# Instalação no Windows + iPad

Tempo estimado: 20 minutos.

## 1. No PC (Windows)

1. Instale o [Python 3.12+](https://www.python.org/downloads/) e marque **"Add python.exe to PATH"**.
2. Instale o [Git](https://git-scm.com/download/win) e clone o projeto:
   ```powershell
   cd $HOME\Documents
   git clone https://github.com/wenderlui/sexta-feira.git
   cd sexta-feira
   copy .env.example .env
   ```
3. (Opcional) Crie uma chave gratuita do [CoinGecko Demo](https://www.coingecko.com/en/api/pricing)
   e coloque em `COINGECKO_API_KEY` no `.env`.
4. Rode `scripts\iniciar.ps1` (botão direito > Executar com o PowerShell).
   Se o Windows bloquear scripts, rode uma vez no PowerShell:
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
5. Abra http://localhost:8000 no navegador do PC para conferir o painel.

## 2. Tailscale (HTTPS para o iPad)

O Safari só libera câmera e microfone em páginas HTTPS. O Tailscale cria uma rede
privada entre os seus aparelhos e dá um certificado HTTPS válido, sem abrir portas no roteador.

1. Instale o [Tailscale](https://tailscale.com/download) no PC e no iPad e entre com a mesma conta.
2. No [painel do Tailscale](https://login.tailscale.com/admin/dns), ative **MagicDNS** e
   **HTTPS Certificates**.
3. No PC, com o servidor rodando, publique a porta 8000 só para a sua rede:
   ```powershell
   tailscale serve --bg 8000
   ```
   O comando mostra um endereço como `https://seu-pc.tailXXXX.ts.net`.

> Use `tailscale serve`, e **não** `tailscale funnel`: o funnel abriria para a internet inteira.

## 3. No iPad

1. Abra o endereço `https://seu-pc.tailXXXX.ts.net` no Safari.
2. Toque em Compartilhar > **Adicionar à Tela de Início**. Abra a Sexta-feira por esse ícone.
3. Toque em **Câmera** e **Microfone** e permita o acesso.
4. Para deixar ligado o tempo todo: deixe o iPad carregando, e em Ajustes > Tela e Brilho >
   Bloqueio Automático escolha **Nunca**. Para travar no app, use
   Ajustes > Acessibilidade > **Acesso Guiado**.

O iOS desliga câmera e microfone quando a tela bloqueia ou o app sai da frente.
Isso é uma regra do sistema; ao voltar para o app, é só tocar nos botões de novo.

## 4. Iniciar junto com o Windows

1. Abra o **Agendador de Tarefas** > Criar Tarefa.
2. Disparador: **Ao fazer logon**.
3. Ação: Iniciar um programa: `powershell.exe`, argumentos:
   `-ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\caminho\para\sexta-feira\scripts\iniciar.ps1"`.
4. O `tailscale serve --bg` já fica salvo e volta sozinho depois de reiniciar.

## Problemas comuns

| Sintoma | Causa provável | Solução |
| --- | --- | --- |
| "Sem acesso à câmera: abra pelo endereço HTTPS" | Abriu por `http://` ou IP | Use o endereço `https://...ts.net` |
| USDT/BRL mostra fonte "CoinGecko" | A Binance bloqueia IPs dos EUA | Normal; a reserva funciona sozinha |
| "Sem dados: cripto" | Limite do CoinGecko | Coloque a chave Demo no `.env` |
| Página antiga depois de atualizar | Cache do app | Feche e abra o app de novo |
