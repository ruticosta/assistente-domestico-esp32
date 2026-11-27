# Assistente Doméstico Inteligente com Processamento Distribuído

Projeto da disciplina **Arquitetura de Computadores** (UFT — Campus de Palmas).

## Arquitetura Adaptada (Sem Microfone INMP441)

Para manter integralmente o princípio de **processamento distribuído** sem o módulo de áudio físico INMP441, a camada de captura de voz foi desacoplada para uma **interface web servida pelo próprio FastAPI**:

```
[Voz no Notebook/Celular]
        │  HTTP POST /api/command/audio (áudio gravado)
        ▼
[Backend FastAPI (Docker)] ──► Speech-to-Text (ffmpeg + SpeechRecognition pt-BR)
        │                  ──► Interpretação semântica (NLP)
        │                  ──► Cálculo da máscara de bits (0..15)
        ▼
[PostgreSQL 16 (Docker)]   ──► Persiste estado dos dispositivos e histórico analítico
        │
        │  HTTP GET /api/hardware/state (Wi-Fi)
        ▼
[ESP32 WROOM DevKit V1]    ──► Barramento paralelo de 4 bits (GPIO 25, 26, 27, 14) + LED de feedback (GPIO 2)
        ▼
[CI 7400 (4 portas NAND)]  ──► Driver Active-LOW: entrada A = bit D_i, entrada B = trava ENABLE (1Y..4Y)
        ▼
[Módulo Relé 4 Canais 5V]  ──► Acionamento das cargas elétricas
```

### Camada de Borda: CI 7400 + Trava `ENABLE` em Hardware

Cada bit da máscara (D0..D3) é aplicado diretamente em um GPIO do ESP32 e entra na **entrada A** de uma porta NAND do CI `7400` (`74HC00`/`74LS00`/`74HCT00`). As **entradas B** das 4 portas são interligadas na linha **`ENABLE`**, que funciona como trava de segurança física:

| `D_i` (ESP32) | `ENABLE` | Saída NAND (`Y_i` → `IN` do relé) | Relé (Active-LOW) |
| :---: | :---: | :---: | :--- |
| `0` | `1` | `1` | Desligado |
| `1` | `1` | `0` | **Ligado** |
| `X` | `0` | `1` | **Todos desligados por hardware** |

| Bit | GPIO | Pino do 7400 (entrada → saída) | Relé | Dispositivo |
| :---: | :---: | :---: | :---: | :--- |
| 0 | 25 | 1 (1A) → 3 (1Y) | IN1 | Luz do Quarto |
| 1 | 26 | 4 (2A) → 6 (2Y) | IN2 | Luz da Sala |
| 2 | 27 | 9 (3A) → 8 (3Y) | IN3 | Luz da Cozinha |
| 3 | 14 | 12 (4A) → 11 (4Y) | IN4 | Ar-Condicionado |

Detalhes completos de montagem em [`docs/esquema_protoboard.md`](docs/esquema_protoboard.md).

---

## Como Rodar o Backend e o Banco (Docker)

1. Entre na pasta do projeto e suba os containers:
   ```bash
   cd assistente-domestico-esp32
   docker compose up --build -d
   ```
2. Acesse no navegador do seu notebook:
   - **Interface de Voz e Monitoramento:** `http://localhost:8000`
   - **Documentação interativa (Swagger):** `http://localhost:8000/docs`
3. Para ver os logs em tempo real:
   ```bash
   docker compose logs -f backend
   ```
4. Para parar os containers:
   ```bash
   docker compose down
   ```

> **Dica para o microfone:** navegadores permitem acesso ao microfone em `http://localhost:8000` sem precisar de HTTPS. Use o microfone do próprio notebook na demonstração (e você ainda tem o campo de texto e os botões manuais como plano B).

---

## Como Configurar o ESP32

1. Descubra o IP do seu notebook na rede Wi-Fi:
   ```bash
   hostname -I
   ```
2. Abra `firmware/esp32_assistente/esp32_assistente.ino` na **Arduino IDE**.
3. Ajuste as 3 linhas de rede no topo do arquivo:
   ```cpp
   const char* WIFI_SSID     = "SUA_REDE";
   const char* WIFI_PASSWORD = "SUA_SENHA";
   const char* API_STATE_URL = "http://IP_DO_NOTEBOOK:8000/api/hardware/state";
   ```
4. Siga as ligações físicas em [`docs/esquema_protoboard.md`](docs/esquema_protoboard.md) e faça o upload para o ESP32.

### Alternativa: Modo Ponte USB (sem Wi-Fi)

Se o Wi-Fi não estiver configurado (SSID padrão `NOME_DA_SUA_REDE_WIFI`), o firmware opera em **Modo Ponte USB Serial**, aceitando a máscara (`0`..`15`) pelo cabo USB. Nesse caso, rode no notebook a ponte que consulta a API e repassa a máscara ao ESP32:

```bash
pip install pyserial
python3 bridge_usb.py
```

A URL da API pode ser alterada pela variável de ambiente `API_STATE_URL` (padrão: `http://localhost:8000/api/hardware/state`).

### Teste de Bancada pelo Monitor Serial

No Monitor Serial (`115200 baud`), digite um número de `0` a `15` para acionar os relés diretamente, ou `E` para simular um comando inválido (o LED de feedback pisca).

---

## Exemplos de Comandos de Voz / Texto Suportados

- `"ligar a luz do quarto"` / `"desligar a luz do quarto"`
- `"acender a luz da sala"` / `"apagar a luz da sala"`
- `"ligar a cozinha"`
- `"ligar o ar condicionado"` / `"alternar o ar condicionado"`
- `"ligar tudo"` / `"desligar todas as luzes"`
- Comandos desconhecidos (ex.: `"abrir a janela"`) são registrados como **INVÁLIDOS** no PostgreSQL e fazem o **LED de feedback** do ESP32 piscar.
