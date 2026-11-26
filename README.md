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
[ESP32 WROOM DevKit V1]    ──► shiftOut() serial (3 GPIOs) + LED de feedback
        ▼
[CI 74HC595 Shift Register]──► Expansão serial → paralela (Q0..Q3)
        ▼
[Módulo Relé 4 Canais 5V]  ──► Acionamento das cargas elétricas
```

---

## Como Rodar o Backend e o Banco (Docker)

1. Entre na pasta do projeto e suba os containers:
   ```bash
   cd /home/ruti/assistente-domestico-esp32
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

---

## Exemplos de Comandos de Voz / Texto Suportados

- `"ligar a luz do quarto"` / `"desligar a luz do quarto"`
- `"acender a luz da sala"` / `"apagar a luz da sala"`
- `"ligar a cozinha"`
- `"ligar o ar condicionado"` / `"alternar o ar condicionado"`
- `"ligar tudo"` / `"desligar todas as luzes"`
- Comandos desconhecidos (ex.: `"abrir a janela"`) são registrados como **INVÁLIDOS** no PostgreSQL e fazem o **LED de feedback** do ESP32 piscar.
