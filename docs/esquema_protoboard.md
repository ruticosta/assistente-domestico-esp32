# Guia de Montagem na Protoboard (ESP32 + CI 7400 NAND + Módulo Relé 4 Canais)

Este guia descreve a ligação física da camada de borda usando o **CI `7400` (`74LS00` ou `74HC00` — 4 portas NAND)** como **driver combinacional Active-LOW com trava de segurança em hardware (`ENABLE`)**.

> **Atenção ao código do chip:** confira a gravação em cima do CI antes de ligar:
> - **`74LS00` / `74HC00` / `74HCT00`** → usam a pinagem abaixo (DIP-14).
> - Se o seu chip for **`CD4011`**, me avise antes de ligar porque as saídas dos pinos 4..6 e 8..10 são invertidas em relação ao `7400`.

---

## 1. Como funciona a lógica NAND + Trava `ENABLE`

| Sinal do ESP32 (`D_i`) | Trava `ENABLE` (Hardware) | Saída da `NAND` (`Y_i` → Relé) | Estado do Relé (Active-LOW) |
| :---: | :---: | :---: | :--- |
| `0` (`LOW`) | `1` (`HIGH`) | `1` (`HIGH`) | Desligado |
| `1` (`HIGH`) | `1` (`HIGH`) | `0` (`LOW`) | **Ligado** |
| `0` ou `1` | `0` (`GND`) | `1` (`HIGH`) | **TODOS DESLIGADOS por hardware** |

---

## 2. Pinagem do CI `7400` (DIP-14)

Encaixe o CI `7400` atravessando o canal central da protoboard, com o **chanfro (meia-lua) voltado para cima** (ou para a esquerda):

```
                 ┌──────U──────┐
 ESP32 GPIO 25 ──│ 1 (1A)   14 │── VCC (5V p/ 74LS00 | 3.3V p/ 74HC00)
        ENABLE ──│ 2 (1B)   13 │── ENABLE (4B)
 Relé 1 (IN1)  ◄─│ 3 (1Y)   12 │── ESP32 GPIO 14 (4A)
 ESP32 GPIO 26 ──│ 4 (2A)   11 │─► Relé 4 (IN4)
        ENABLE ──│ 5 (2B)   10 │── ENABLE (3B)
 Relé 2 (IN2)  ◄─│ 6 (2Y)    9 │── ESP32 GPIO 27 (3A)
           GND ──│ 7 (GND)   8 │─► Relé 3 (IN3)
                 └─────────────┘
```

---

## 3. Passo a Passo das Ligações (Fio por Fio)

### Passo 1 — Alimentação (Trilhas da Protoboard)
1. Ligue o pino **`GND`** do ESP32 na trilha **azul (`-`)** da protoboard.
2. Ligue o pino **`VIN`** (`5V` da USB) do ESP32 na trilha **vermelha (`+`)** da protoboard.
3. **CI `7400`:**
   - Pino **`7` (`GND`)** → trilha **`-` (`GND`)**.
   - Pino **`14` (`VCC`)**:
     - Se for **`74LS00`** ou **`74HCT00`**: ligue na trilha **`5V` (`VIN`)**.
     - Se for **`74HC00`**: ligue no **`3V3`** do ESP32 (ou `5V` se precisar de mais tensão no módulo relé).
4. **Módulo Relé 4 Canais:**
   - `VCC` do módulo → trilha **`5V` (`VIN`)**.
   - `GND` do módulo → trilha **`-` (`GND`)**.

### Passo 2 — Linha `ENABLE` (Trava de Segurança em Hardware)
Interligue os 4 pinos de entrada B do CI `7400` entre si:
- Pinos **`2` (`1B`)**, **`5` (`2B`)**, **`10` (`3B`)** e **`13` (`4B`)** juntos em uma mesma coluna (ou na trilha positiva).
- **Para operação normal:** ligue esse ponto de `ENABLE` no **`3V3`** (ou **`5V`** se `VCC = 5V`).
- **Para demonstrar a trava de emergência ao professor:** mova o fio de `ENABLE` para **`GND`** (ou use um botão/chave seletora) — todos os 4 relés desligam na hora via hardware, mesmo que o ESP32 mande ligar!

### Passo 3 — ESP32 ↔ CI `7400` (Barramento de 4 Bits)
*(Os 4 pinos `25, 26, 27, 14` ficam um do lado do outro no lado esquerdo do ESP32 DevKit V1!)*

| ESP32 DevKit V1 | CI `7400` | Dispositivo no Banco | Bit na Máscara |
|---|---|---|---|
| `GPIO 25` (`D0`) | Pino `1` (`1A`) | Luz do Quarto | Bit 0 (`0b0001` = 1) |
| `GPIO 26` (`D1`) | Pino `4` (`2A`) | Luz da Sala | Bit 1 (`0b0010` = 2) |
| `GPIO 27` (`D2`) | Pino `9` (`3A`) | Luz da Cozinha | Bit 2 (`0b0100` = 4) |
| `GPIO 14` (`D3`) | Pino `12` (`4A`) | Ar-Condicionado | Bit 3 (`0b1000` = 8) |

### Passo 4 — CI `7400` ↔ Módulo Relé 4 Canais
| Saída do CI `7400` | Módulo Relé 4 Canais | Canal |
|---|---|---|
| Pino `3` (`1Y`) | `IN1` | Luz do Quarto |
| Pino `6` (`2Y`) | `IN2` | Luz da Sala |
| Pino `8` (`3Y`) | `IN3` | Luz da Cozinha |
| Pino `11` (`4Y`) | `IN4` | Ar-Condicionado |

### Passo 5 — LED de Feedback Visual (Opcional)
O ESP32 já tem o **LED azul embutido no `GPIO 2`**. Para colocar um LED externo na protoboard:
- `ESP32 GPIO 2` → **Resistor 220Ω ou 330Ω** → **Ânodo (`+`, perna maior)** do LED → **Cátodo (`-`, perna menor)** → `GND`.

---

## 4. Teste Rápido de Bancada (Antes do Wi-Fi)

1. Carregue [`esp32_assistente.ino`](../firmware/esp32_assistente/esp32_assistente.ino) no ESP32 pela Arduino IDE.
2. Abra o **Monitor Serial** em `115200 baud`.
3. Digite números de `0` a `15` e aperte Enter:
   - `0` → Todos desligados (`0000`)
   - `1` → Relé 1 ligado (`0001`)
   - `2` → Relé 2 ligado (`0010`)
   - `4` → Relé 3 ligado (`0100`)
   - `8` → Relé 4 ligado (`1000`)
   - `15` → Todos os 4 relés ligados (`1111`)
4. Teste a trava **`ENABLE`**: com `15` ativo (todos ligados), encoste o fio `ENABLE` no `GND` → todos os 4 relés devem desligar imediatamente!
