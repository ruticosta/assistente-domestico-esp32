/*
 * Assistente Doméstico Inteligente com Processamento Distribuído
 * Disciplina: Arquitetura de Computadores - UFT (Campus de Palmas)
 *
 * Hardware (Versão com CI 7400 - 4 Portas NAND + Trava ENABLE em Hardware):
 *  - ESP32 WROOM DevKit V1
 *  - CI 7400 (74LS00 ou 74HC00 — 4 portas NAND de 2 entradas, DIP-14)
 *  - Módulo Relé 4 Canais 5V (Active-LOW, ligado às saídas 1Y..4Y do 7400)
 *  - LED de Feedback Visual (GPIO 2 - LED azul embutido na placa ou externo)
 *
 * Lógica da Porta NAND (7400) + Módulo Relé Active-LOW:
 *  - Cada canal do ESP32 (D0..D3) entra na entrada A de uma porta NAND.
 *  - Todas as entradas B ficam ligadas juntas na linha ENABLE (trava física).
 *  - Quando ENABLE = HIGH (1) e D_i = HIGH (1) -> Saída NAND = LOW (0) -> Relé LIGA.
 *  - Quando ENABLE = HIGH (1) e D_i = LOW  (0) -> Saída NAND = HIGH (1) -> Relé DESLIGA.
 *  - Quando ENABLE = LOW  (0) (emergência)     -> Saída NAND = HIGH (1) -> TODOS DESLIGAM por hardware!
 *
 * Funcionamento:
 *  1. Conecta ao Wi-Fi local.
 *  2. Consulta periodicamente GET /api/hardware/state na API FastAPI.
 *  3. Extrai cada bit da máscara (bit 0..3) e aplica nos 4 GPIOs (D0..D3).
 *  4. Se o último comando recebido pela API for inválido, pisca o LED de feedback.
 *  5. Aceita comandos diretos pelo Monitor Serial (0 a 15) para teste de bancada.
 */

#include <WiFi.h>
#include <HTTPClient.h>

// ===================== CONFIGURAÇÃO DE REDE =====================
const char* WIFI_SSID     = "NOME_DA_SUA_REDE_WIFI";
const char* WIFI_PASSWORD = "SENHA_DA_SUA_REDE_WIFI";

// Troque pelo IP local do notebook/servidor rodando o FastAPI (ex: 192.168.43.10)
const char* API_STATE_URL = "http://192.168.0.100:8000/api/hardware/state";

// ===================== PINAGEM DO HARDWARE ======================
// Barramento paralelo de 4 bits: ESP32 -> Entradas A das 4 portas NAND (CI 7400)
const int PIN_D0 = 25; // Bit 0 -> Pino 1  (1A) do 7400 -> Relé 1 (Luz do Quarto)
const int PIN_D1 = 26; // Bit 1 -> Pino 4  (2A) do 7400 -> Relé 2 (Luz da Sala)
const int PIN_D2 = 27; // Bit 2 -> Pino 9  (3A) do 7400 -> Relé 3 (Luz da Cozinha)
const int PIN_D3 = 14; // Bit 3 -> Pino 12 (4A) do 7400 -> Relé 4 (Ar-Condicionado)

const int CHANNEL_PINS[4] = { PIN_D0, PIN_D1, PIN_D2, PIN_D3 };

// LED de Feedback Visual (GPIO 2 = LED azul embutido no ESP32 DevKit V1)
const int PIN_LED_FEEDBACK = 2;

// Como a porta NAND já inverte o sinal na saída (1 NAND 1 = 0 = LOW),
// para Módulos Relé Active-LOW (padrão) o ESP32 envia lógica NORMAL (HIGH = ligar).
// Se você estiver usando módulo relé Active-HIGH (ou LEDs comuns ligados ao GND),
// altere para false (o ESP32 inverte antes da NAND para cancelar a inversão).
#define RELAY_ACTIVE_LOW true

// Intervalo de consulta à API em milissegundos
const unsigned long POLL_INTERVAL_MS = 500;

// ===================== VARIÁVEIS DE ESTADO ======================
uint8_t currentBitmask = 0x00;
long lastCommandId = -1;
unsigned long lastPollTime = 0;

// Aplica os 4 bits da máscara nos GPIOs ligados às entradas do CI 7400 (NAND)
void atualizarSaidasNAND(uint8_t bitmask) {
  uint8_t valorLogico = bitmask & 0x0F;

  for (int i = 0; i < 4; i++) {
    bool ligar = (valorLogico >> i) & 1;
    // Com RELAY_ACTIVE_LOW = true, a própria porta NAND faz a inversão para LOW.
    bool nivelGpio = RELAY_ACTIVE_LOW ? ligar : !ligar;
    digitalWrite(CHANNEL_PINS[i], nivelGpio ? HIGH : LOW);
  }

  Serial.print("[7400 NAND] Bitmask: ");
  Serial.print(valorLogico);
  Serial.print(" (0b");
  for (int i = 3; i >= 0; i--) {
    Serial.print((valorLogico >> i) & 1);
  }
  Serial.print(") | D0(Qto)=");
  Serial.print((valorLogico >> 0) & 1);
  Serial.print(" D1(Sala)=");
  Serial.print((valorLogico >> 1) & 1);
  Serial.print(" D2(Coz)=");
  Serial.print((valorLogico >> 2) & 1);
  Serial.print(" D3(Ar)=");
  Serial.println((valorLogico >> 3) & 1);
}

// Pisca o LED para sinalizar comando inválido
void sinalizarComandoInvalido() {
  Serial.println("[FEEDBACK] Comando invalido recebido pela API! Piscando LED...");
  for (int i = 0; i < 4; i++) {
    digitalWrite(PIN_LED_FEEDBACK, HIGH);
    delay(120);
    digitalWrite(PIN_LED_FEEDBACK, LOW);
    delay(120);
  }
}

// Pisca curto para confirmar atualização válida
void sinalizarComandoValido() {
  digitalWrite(PIN_LED_FEEDBACK, HIGH);
  delay(80);
  digitalWrite(PIN_LED_FEEDBACK, LOW);
}

// Extrai inteiro simples de um campo JSON sem precisar de biblioteca externa
long extrairIntJson(const String& json, const String& chave, long padrao) {
  String busca = "\"" + chave + "\":";
  int idx = json.indexOf(busca);
  if (idx < 0) return padrao;
  idx += busca.length();
  while (idx < (int)json.length() && json[idx] == ' ') idx++;
  int fim = idx;
  while (fim < (int)json.length() && (isDigit(json[fim]) || json[fim] == '-')) fim++;
  if (fim == idx) return padrao;
  return json.substring(idx, fim).toInt();
}

// Extrai booleano simples de um campo JSON
bool extrairBoolJson(const String& json, const String& chave, bool padrao) {
  String busca = "\"" + chave + "\":";
  int idx = json.indexOf(busca);
  if (idx < 0) return padrao;
  idx += busca.length();
  while (idx < (int)json.length() && json[idx] == ' ') idx++;
  if (json.startsWith("true", idx)) return true;
  if (json.startsWith("false", idx)) return false;
  return padrao;
}

void conectarWiFi() {
  if (String(WIFI_SSID) == "NOME_DA_SUA_REDE_WIFI" || String(WIFI_SSID).length() == 0) {
    Serial.println("[USB] Wi-Fi nao configurado. Rodando imediatamente em Modo Ponte USB Serial!");
    return;
  }

  Serial.print("[WiFi] Conectando a ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED && tentativas < 30) {
    delay(500);
    Serial.print(".");
    tentativas++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Conectado! IP do ESP32: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WiFi] Nao conectou ainda. Modo Serial de teste segue ativo (digite 0..15).");
  }
}

void consultarEstadoAPI() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  HTTPClient http;
  http.setTimeout(1500);
  http.begin(API_STATE_URL);
  int httpCode = http.GET();

  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();
    uint8_t novaMascara = (uint8_t)extrairIntJson(payload, "bitmask", currentBitmask);
    long cmdId = extrairIntJson(payload, "last_command_id", lastCommandId);
    bool cmdValido = extrairBoolJson(payload, "last_command_valid", true);

    if (novaMascara != currentBitmask) {
      currentBitmask = novaMascara;
      atualizarSaidasNAND(currentBitmask);
      sinalizarComandoValido();
    }

    if (lastCommandId != -1 && cmdId != lastCommandId && !cmdValido) {
      sinalizarComandoInvalido();
    }
    lastCommandId = cmdId;
  } else {
    Serial.print("[HTTP] Erro ao consultar API. Codigo: ");
    Serial.println(httpCode);
  }

  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(300);

  for (int i = 0; i < 4; i++) {
    pinMode(CHANNEL_PINS[i], OUTPUT);
  }
  pinMode(PIN_LED_FEEDBACK, OUTPUT);
  digitalWrite(PIN_LED_FEEDBACK, LOW);

  // Garante todos os relés desligados ao iniciar
  atualizarSaidasNAND(0x00);

  Serial.println("\n=== Assistente Domestico Inteligente (ESP32 + CI 7400 NAND) ===");
  Serial.println("Dica: voce pode digitar um numero de 0 a 15 no Monitor Serial para testar os reles.");
  conectarWiFi();
}

void loop() {
  // Modo Ponte USB Serial / teste local (aceita 0..15 ou 'E' para comando invalido)
  if (Serial.available() > 0) {
    String entrada = Serial.readStringUntil('\n');
    entrada.trim();
    if (entrada.length() > 0) {
      if (entrada == "E" || entrada == "e") {
        sinalizarComandoInvalido();
      } else {
        int valor = entrada.toInt();
        if (valor >= 0 && valor <= 15) {
          currentBitmask = (uint8_t)valor;
          atualizarSaidasNAND(currentBitmask);
          sinalizarComandoValido();
        } else {
          Serial.println("[SERIAL] Digite um valor entre 0 e 15.");
        }
      }
    }
  }

  // Polling periódico à API FastAPI
  unsigned long agora = millis();
  if (agora - lastPollTime >= POLL_INTERVAL_MS) {
    lastPollTime = agora;
    consultarEstadoAPI();
  }
}
