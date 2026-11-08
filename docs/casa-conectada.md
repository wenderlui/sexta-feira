# Casa conectada

A Sexta-feira controla a casa de dois jeitos, configurados em **AJUSTES > CONEXÕES** no iPad:

1. **Home Assistant** (recomendado): a central que conversa com quase tudo.
2. **Govee direto**: só os LEDs Govee, pela chave da API da Govee.

Depois de conectar, os aparelhos aparecem em **AJUSTES > CASA** (toque para ligar/desligar) e
você pode pedir por voz: "Sexta-feira, acende a luz da sala", "desliga a TV", "põe o ar em 22 graus".

## Home Assistant no PC Windows

O jeito mais simples no Windows é o Home Assistant OS numa máquina virtual (VirtualBox ou Hyper-V),
que liga junto com o PC. Depois de instalar, abra `http://homeassistant.local:8123`, crie a conta e:

| Aparelho | Integração no Home Assistant |
|---|---|
| TV Samsung | SmartThings (ou Samsung Smart TV) |
| TV TCL | Android TV Remote / Google Cast (Google TV) ou Roku (Roku TV) |
| Câmeras Blink | Blink |
| LEDs Govee | Govee Lights Local (pela rede) ou a conexão Govee direta da Sexta-feira |
| Ar-condicionado | Integração da marca, ou um controle IR (Broadlink, SwitchBot) |
| PC | Wake on LAN para ligar; HASS.Agent para desligar/bloquear |

Para conectar a Sexta-feira: no Home Assistant, clique no seu nome > **Segurança** >
**Tokens de acesso de longa duração** > **Criar token**. Cole o endereço e o token em
AJUSTES > CONEXÕES > Home Assistant e toque em **SALVAR E TESTAR**.

O token fica guardado só no PC (`data/ajustes.json`) e nunca volta para o iPad.
