#!/usr/bin/env python3
"""
Ponte USB Serial <-> API FastAPI (Assistente Doméstico Inteligente)

Lê continuamente GET http://localhost:8000/api/hardware/state e envia a máscara
de bits (0..15) direto pela porta USB (/dev/ttyUSB* ou /dev/ttyACM*) para o ESP32.
Usa pyserial com DTR/RTS desativados para não travar o ESP32 em modo reset/boot.
"""

import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request

import serial

API_URL = os.getenv("API_STATE_URL", "http://localhost:8000/api/hardware/state")
POLL_SECONDS = 0.25


def encontrar_porta_serial() -> str | None:
    if len(sys.argv) > 1:
        return sys.argv[1]
    candidatas = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    return candidatas[0] if candidatas else None


def consultar_api() -> dict:
    with urllib.request.urlopen(API_URL, timeout=2.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ler_resposta_esp32(ser: serial.Serial) -> None:
    while ser.in_waiting > 0:
        linha = ser.readline().decode("utf-8", errors="replace").strip()
        if linha:
            print(f"[ESP32] {linha}")


def main() -> None:
    porta = encontrar_porta_serial()
    if not porta:
        print("[ERRO] Nenhum ESP32 encontrado em /dev/ttyUSB* ou /dev/ttyACM*.")
        print("       Conecte o ESP32 com um cabo USB de dados e tente novamente.")
        sys.exit(1)

    print(f"[USB] Conectando ao ESP32 em {porta} (115200 baud)...")
    try:
        ser = serial.Serial()
        ser.port = porta
        ser.baudrate = 115200
        ser.timeout = 0.1
        ser.dtr = False
        ser.rts = False
        ser.open()
        # Garante DTR/RTS baixos para não prender o ESP32 em bootloader/reset
        ser.dtr = False
        ser.rts = False
    except PermissionError:
        print(f"[ERRO] Sem permissão para abrir {porta}.")
        print(f"       Rode no terminal: sudo chmod 666 {porta}")
        sys.exit(1)

    time.sleep(0.5)
    ler_resposta_esp32(ser)
    print(f"[OK] Ponte ativa! Sincronizando {API_URL} -> {porta} (Ctrl+C para sair)")

    ultima_mascara = None
    ultimo_cmd_id = None

    try:
        while True:
            try:
                estado = consultar_api()
                mascara = int(estado.get("bitmask", 0)) & 0x0F
                cmd_id = estado.get("last_command_id")
                cmd_valido = estado.get("last_command_valid", True)

                if mascara != ultima_mascara:
                    ser.write(f"{mascara}\n".encode("ascii"))
                    ser.flush()
                    ultima_mascara = mascara
                    print(f"[SYNC] Enviado para ESP32 -> bitmask={mascara} (0b{mascara:04b})")
                    time.sleep(0.08)

                if ultimo_cmd_id is not None and cmd_id != ultimo_cmd_id and not cmd_valido:
                    ser.write(b"E\n")
                    ser.flush()
                    print("[SYNC] Comando inválido detectado -> piscando LED de feedback no ESP32")

                ultimo_cmd_id = cmd_id
                ler_resposta_esp32(ser)
            except urllib.error.URLError as e:
                print(f"[API] Aguardando backend ({e})...")
            except (serial.SerialException, OSError) as e:
                print(f"[USB] Erro na porta serial: {e}")
                break

            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\n[USB] Ponte encerrada.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
