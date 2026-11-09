# Sexta-feira: plano do projeto

Documento de gestão do projeto, no formato das áreas do PMBOK (escopo, cronograma, qualidade,
riscos, comunicações), com rastreabilidade de requisitos para testes e o modelo de segurança.

## 1. Termo de abertura

| Item | Definição |
|---|---|
| Objetivo | Assistente pessoal de IA, estilo "Jarvis", disponível 24/7, com o iPad deitado como visor. |
| Patrocinador e usuário | Wender (dono do PC, do iPad e das contas). |
| Restrições | Modelos gratuitos ou locais; dados financeiros e e-mail só leitura; a IA nunca paga, compra ou envia nada sozinha. |
| Premissas | PC Windows ligado 24/7 (i7-13700F, 32 GB, RTX 4070 Ti); iPad e PC na mesma rede privada Tailscale. |
| Critério de sucesso | Conversa por voz em português com resposta em até ~3 s, painel ao vivo confiável, controle da casa por voz. |

## 2. Escopo (EAP)

1. **Painel ao vivo**: clima de Lowell, MA; cripto (POL, UNI, ETH, BTC, DOT, LINK); USDT/BRL; estado do PC. *Entregue.*
2. **Voz e IA**: escuta com "Sexta-feira", Whisper na GPU, Ollama (qwen3:8b), visão pela câmera, busca na web, voz natural. *Entregue.*
3. **Ajustes e casa conectada**: tela de AJUSTES, Home Assistant como central (TVs Samsung/TCL, Blink, ar, PC), Govee direto, controle por voz. *Entregue; Home Assistant a instalar.*
4. **Contas e finanças**: Gmail (contas a vencer), banco via Open Finance, só leitura. *Próxima etapa.*
5. **Redes sociais e IPTV**: resumo de notificações; canais na TV via player. *Planejado.*

Fora do escopo por enquanto: placar de futebol (pedido do usuário), pagamentos automáticos.

## 3. Cronograma por marcos

| Marco | Situação |
|---|---|
| M1 Pesquisa e arquitetura | Concluído (2026-11-07) |
| M2 Painel no iPad + servidor iniciando com o Windows | Concluído (2026-11-07) |
| M3 Voz contínua, voz natural, atualização automática do app | Concluído (2026-11-07) |
| M4 Ajustes, liquid glass, casa conectada | Concluído no código (2026-11-08); falta instalar o Home Assistant |
| M5 Gmail e finanças (só leitura) | A iniciar |

## 4. Requisitos e rastreabilidade

| Requisito | Como é verificado |
|---|---|
| Painel mostra clima e preços, com reserva quando a API cai | `tests/test_api.py`, `tests/test_cache.py` |
| Responde em português com busca quando precisa | `tests/test_assistant.py`, `tests/test_research.py` |
| Ouve frase inteira, inclusive o começo ("Sexta-feira…") | `web/tests/listen.test.mjs` |
| Voz natural com reserva local sem internet | `test_speaker_falls_back_to_local_voice` |
| Ajustes ficam salvos no PC e sobrevivem a reinício | `test_preferences_are_saved_on_the_pc`, `scripts/verificar-tela.mjs` |
| Senhas e chaves nunca voltam ao iPad | `test_connection_secret_never_goes_back_to_the_ipad` |
| Controle de aparelhos pela tela e por voz | `test_devices_from_home_assistant_and_govee`, `test_ai_controls_the_house` |
| Botões alinhados, alvo de toque ≥ 44 px, sem rolagem no iPad deitado | `scripts/verificar-tela.mjs` |
| Funciona no celular em pé: sem rolagem lateral, barra e ajustes dentro da tela | `scripts/verificar-tela.mjs` |

## 5. Qualidade

- **Testes automáticos**: `pytest` (servidor, com APIs externas simuladas) e `npm test` (lógica do app). Rodam no GitHub a cada envio (`.github/workflows/testes.yml`).
- **Verificação de tela**: `node scripts/verificar-tela.mjs http://127.0.0.1:8000 [pasta]` abre o app no tamanho do iPad e confere rolagem, sobreposição de painéis, alinhamento dos botões, tela de AJUSTES e se as preferências ficam salvas. Opcionalmente salva fotos.
- **Diagnóstico em produção**: o iPad manda avisos para `/api/log`, que vão para `logs/servidor.log` no PC.
- **Padrões**: código e textos em português, sem segredos no Git (`.env`, `data/`, `logs/`, `models/` ignorados), mudanças por pull request.

## 6. Onde cada dado fica

| Dado | Onde |
|---|---|
| Voz, velocidade, conexões (com senhas/chaves) | PC, `data/ajustes.json` (permissão só do dono) |
| Chaves de serviços (CoinGecko etc.) | PC, `.env` |
| Últimas 20 mensagens, câmera ligada, gráficos | iPad, armazenamento local do navegador |
| Registro de funcionamento e último áudio | PC, `logs/` |
| Modelos de IA e voz | PC, Ollama e `models/` |
| Áudio e imagem da câmera | Só trafegam iPad → PC pelo Tailscale; não são guardados |
| Texto das respostas faladas | Com a voz natural, vai para a Microsoft gerar o áudio |

## 7. Segurança (modelo de ameaças)

- **Exposição**: o servidor escuta só em `127.0.0.1`; o acesso de fora é pelo Tailscale Serve, que só aceita aparelhos da sua rede privada. Nunca usar `tailscale funnel` (abriria para a internet).
- **Segredos**: guardados só no PC; a API devolve apenas "••••" e os 4 últimos caracteres. Campo de senha vazio mantém o valor salvo.
- **Entrada validada**: preferências com lista fechada de valores; URL do Home Assistant só `http(s)://`; ID de aparelho validado por expressão regular; ações limitadas (ligar, desligar, alternar, brilho, temperatura) e valores com limites (ar entre 16 e 30 °C).
- **Ações perigosas**: a IA não tem ferramenta para pagar, comprar ou enviar mensagens. Câmeras são só leitura.
- **Navegador**: cabeçalhos `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, permissões só para câmera e microfone; respostas da API com `no-store`.
- **Arquivos**: o servidor de arquivos estáticos não sai da pasta `web/` (testado).
- **Gravação segura**: ajustes gravados de forma atômica; arquivo corrompido é guardado à parte e o sistema volta ao padrão.

## 8. Riscos

| Risco | Prob. | Impacto | Resposta |
|---|---|---|---|
| Internet cai | Média | Médio | Voz local (Kokoro) e IA local continuam; painel mostra o último valor. |
| PC reinicia ou atualiza | Média | Alto | Tarefa do Windows religa o servidor (até 999 tentativas e checagem a cada 5 min); PC nunca suspende na tomada. Sem login automático, só sobe quando o usuário entra no Windows. |
| Servidor cai no logoff | Baixa | Alto | Corrigido: `FOR_DISABLE_CONSOLE_CTRL_HANDLER=1` em `iniciar.ps1`. |
| iPad fica com versão antiga do app | Baixa | Médio | Service worker se atualiza sozinho. |
| Serviço externo muda a API (Govee, CoinGecko) | Média | Baixo | Erros aparecem nos ajustes e no registro; testes simulados mostram o formato esperado. |
| Vazamento de token | Baixa | Alto | Token só no PC, nunca no iPad nem no Git; tokens podem ser revogados no Home Assistant/Govee. |
| IA entende um comando errado na casa | Média | Baixo | Só ações reversíveis (ligar/desligar); ela confirma o que fez. |

## 9. Comunicação

Andamento e decisões ficam no projeto do Claude (thread do projeto) e no pull request no GitHub.
Mudanças que afetam o PC são aplicadas e testadas no próprio PC antes de pedir teste no iPad.

## 10. Lições aprendidas

- No iPad, a voz do Safari fica muda com o microfone ligado: a voz é gerada no PC.
- Gravar só depois de detectar fala corta o começo: a captura é contínua com 1 s de pré-gravação.
- O Ollama recarrega o modelo se o tamanho de contexto muda: o pré-carregamento usa o mesmo valor.
- No Windows, o `urllib` falha em HTTPS por certificado: downloads usam `httpx`.
