import os
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Dispositivo, HistoricoComando
from .nlp import interpretar_comando
from .stt import ErroTranscricao, transcrever_audio_bytes

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Assistente Doméstico Inteligente - API Distribuída",
    description="Backend FastAPI para transcrição de voz, interpretação semântica, persistência PostgreSQL e controle de máscara de bits para ESP32 + 74HC595.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Telemetria em memória da conexão do ESP32
esp32_telemetry = {
    "last_poll_ts": None,
    "ip": None,
    "poll_count": 0,
}


class ComandoTextoRequest(BaseModel):
    text: str
    origem: str = "web_texto"


class TimerRequest(BaseModel):
    duration_seconds: int


def verificar_timers_expirados(db: Session) -> None:
    agora = datetime.now(timezone.utc)
    expirados = (
        db.query(Dispositivo)
        .filter(
            Dispositivo.estado.is_(True),
            Dispositivo.desligar_em.is_not(None),
            Dispositivo.desligar_em <= agora,
        )
        .all()
    )
    if not expirados:
        return

    for disp in expirados:
        disp.estado = False
        disp.desligar_em = None
    db.flush()

    todos = db.query(Dispositivo).order_by(Dispositivo.bit_posicao.asc()).all()
    mascara = calcular_mascara_bits(todos)
    for disp in expirados:
        db.add(
            HistoricoComando(
                origem="timer_auto",
                texto_transcrito=f"[Timer] Desligamento automático: {disp.nome}",
                comando_valido=True,
                acao_interpretada="desligar",
                dispositivo_id=disp.id,
                mascara_bits_resultante=mascara,
                mensagem_retorno=f"'{disp.nome}' desligado automaticamente ao fim do timer.",
            )
        )
    db.commit()


def calcular_mascara_bits(dispositivos: List[Dispositivo]) -> int:
    mascara = 0
    for d in dispositivos:
        if d.estado:
            mascara |= 1 << d.bit_posicao
    return mascara


def formatar_binario(mascara: int) -> str:
    return format(mascara & 0xFF, "08b")


def status_esp32() -> dict:
    last_ts = esp32_telemetry["last_poll_ts"]
    if last_ts is None:
        return {
            "online": False,
            "last_seen_seconds": None,
            "ip": None,
            "poll_count": 0,
        }
    delta = round(time.time() - last_ts, 1)
    return {
        "online": delta <= 3.5,
        "last_seen_seconds": delta,
        "ip": esp32_telemetry["ip"],
        "poll_count": esp32_telemetry["poll_count"],
    }


def serializar_dispositivo(d: Dispositivo) -> dict:
    restante = None
    if d.estado and d.desligar_em is not None:
        delta = int((d.desligar_em - datetime.now(timezone.utc)).total_seconds())
        restante = max(0, delta)
    return {
        "id": d.id,
        "nome": d.nome,
        "localizacao": d.localizacao,
        "apelidos": d.apelidos,
        "bit_posicao": d.bit_posicao,
        "estado": d.estado,
        "temperatura": d.temperatura,
        "desligar_em": d.desligar_em.isoformat() if d.desligar_em else None,
        "timer_restante_segundos": restante,
        "atualizado_em": d.atualizado_em.isoformat() if d.atualizado_em else None,
    }


def processar_e_persistir_comando(db: Session, texto: str, origem: str, inicio_ts: float) -> dict:
    verificar_timers_expirados(db)
    dispositivos = db.query(Dispositivo).order_by(Dispositivo.bit_posicao.asc()).all()
    resultado = interpretar_comando(texto, dispositivos)
    mensagem_final = resultado.mensagem

    if resultado.valido:
        alvos = dispositivos if resultado.alvo_todos else [resultado.dispositivo]
        for disp in alvos:
            if disp is None:
                continue
            if resultado.acao == "ligar":
                disp.estado = True
            elif resultado.acao == "desligar":
                disp.estado = False
                disp.desligar_em = None
            elif resultado.acao == "alternar":
                disp.estado = not disp.estado
                if not disp.estado:
                    disp.desligar_em = None
            elif resultado.acao == "temperatura":
                disp.estado = True
                if resultado.temperatura_alvo is not None:
                    disp.temperatura = max(16, min(30, resultado.temperatura_alvo))
                elif resultado.delta_temperatura is not None:
                    disp.temperatura = max(16, min(30, disp.temperatura + resultado.delta_temperatura))
                    mensagem_final = f"Ar-Condicionado ajustado para {disp.temperatura}°C."
            elif resultado.acao == "timer":
                if resultado.duracao_segundos and resultado.duracao_segundos > 0:
                    disp.estado = True
                    disp.desligar_em = datetime.now(timezone.utc) + timedelta(
                        seconds=resultado.duracao_segundos
                    )
                else:
                    disp.desligar_em = None
        db.flush()

    mascara = calcular_mascara_bits(dispositivos)

    historico = HistoricoComando(
        origem=origem,
        texto_transcrito=texto,
        comando_valido=resultado.valido,
        acao_interpretada=resultado.acao,
        dispositivo_id=resultado.dispositivo.id if resultado.dispositivo else None,
        mascara_bits_resultante=mascara,
        mensagem_retorno=mensagem_final,
    )
    db.add(historico)
    db.commit()
    db.refresh(historico)

    elapsed_ms = round((time.perf_counter() - inicio_ts) * 1000, 1)

    return {
        "command_id": historico.id,
        "valid": resultado.valido,
        "transcribed_text": texto,
        "action": resultado.acao,
        "target_name": (
            "Todos os dispositivos"
            if resultado.alvo_todos
            else (resultado.dispositivo.nome if resultado.dispositivo else None)
        ),
        "message": mensagem_final,
        "processing_time_ms": elapsed_ms,
        "bitmask": mascara,
        "binary": formatar_binario(mascara),
        "hex": f"0x{mascara:02X}",
        "devices": [serializar_dispositivo(d) for d in dispositivos],
    }


@app.get("/")
def index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
    return {"status": "online", "docs": "/docs"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/devices")
def listar_dispositivos(db: Session = Depends(get_db)):
    verificar_timers_expirados(db)
    dispositivos = db.query(Dispositivo).order_by(Dispositivo.bit_posicao.asc()).all()
    mascara = calcular_mascara_bits(dispositivos)
    return {
        "bitmask": mascara,
        "binary": formatar_binario(mascara),
        "hex": f"0x{mascara:02X}",
        "esp32": status_esp32(),
        "devices": [serializar_dispositivo(d) for d in dispositivos],
    }


@app.get("/api/stats")
def estatisticas(db: Session = Depends(get_db)):
    verificar_timers_expirados(db)
    total = db.query(func.count(HistoricoComando.id)).scalar() or 0
    validos = (
        db.query(func.count(HistoricoComando.id))
        .filter(HistoricoComando.comando_valido.is_(True))
        .scalar()
        or 0
    )
    invalidos = total - validos
    ativos = (
        db.query(func.count(Dispositivo.id)).filter(Dispositivo.estado.is_(True)).scalar() or 0
    )
    total_dispositivos = db.query(func.count(Dispositivo.id)).scalar() or 0
    taxa_acerto = round((validos / total) * 100, 1) if total > 0 else 100.0

    return {
        "total_commands": total,
        "valid_commands": validos,
        "invalid_commands": invalidos,
        "accuracy_percent": taxa_acerto,
        "active_devices": ativos,
        "total_devices": total_dispositivos,
        "esp32": status_esp32(),
    }


@app.get("/api/hardware/state")
def estado_hardware(request: Request, db: Session = Depends(get_db)):
    """
    Endpoint otimizado consumido pelo ESP32 via Wi-Fi.
    Registra a telemetria de conexão do ESP32 e retorna a máscara de bits atual
    para o CI 74HC595 + status do último comando (para o LED de feedback).
    """
    esp32_telemetry["last_poll_ts"] = time.time()
    esp32_telemetry["ip"] = request.client.host if request.client else None
    esp32_telemetry["poll_count"] += 1

    verificar_timers_expirados(db)
    dispositivos = db.query(Dispositivo).order_by(Dispositivo.bit_posicao.asc()).all()
    mascara = calcular_mascara_bits(dispositivos)
    ultimo: Optional[HistoricoComando] = (
        db.query(HistoricoComando).order_by(HistoricoComando.id.desc()).first()
    )
    return {
        "bitmask": mascara,
        "binary": formatar_binario(mascara),
        "last_command_id": ultimo.id if ultimo else 0,
        "last_command_valid": ultimo.comando_valido if ultimo else True,
    }


@app.post("/api/command/text")
def comando_texto(payload: ComandoTextoRequest, db: Session = Depends(get_db)):
    inicio = time.perf_counter()
    return processar_e_persistir_comando(db, payload.text, payload.origem, inicio)


@app.post("/api/command/audio")
async def comando_audio(audio: UploadFile = File(...), db: Session = Depends(get_db)):
    inicio = time.perf_counter()
    conteudo = await audio.read()
    _, ext = os.path.splitext(audio.filename or "audio.webm")
    if not ext:
        ext = ".webm"

    try:
        texto = transcrever_audio_bytes(conteudo, ext)
    except ErroTranscricao as e:
        dispositivos = db.query(Dispositivo).order_by(Dispositivo.bit_posicao.asc()).all()
        mascara = calcular_mascara_bits(dispositivos)
        historico = HistoricoComando(
            origem="web_voz",
            texto_transcrito="(áudio não reconhecido)",
            comando_valido=False,
            acao_interpretada=None,
            dispositivo_id=None,
            mascara_bits_resultante=mascara,
            mensagem_retorno=str(e),
        )
        db.add(historico)
        db.commit()
        db.refresh(historico)
        elapsed_ms = round((time.perf_counter() - inicio) * 1000, 1)
        return {
            "command_id": historico.id,
            "valid": False,
            "transcribed_text": "",
            "action": None,
            "target_name": None,
            "message": str(e),
            "processing_time_ms": elapsed_ms,
            "bitmask": mascara,
            "binary": formatar_binario(mascara),
            "hex": f"0x{mascara:02X}",
            "devices": [serializar_dispositivo(d) for d in dispositivos],
        }

    return processar_e_persistir_comando(db, texto, "web_voz", inicio)


@app.post("/api/devices/{device_id}/toggle")
def alternar_dispositivo(device_id: int, db: Session = Depends(get_db)):
    inicio = time.perf_counter()
    disp = db.query(Dispositivo).filter(Dispositivo.id == device_id).first()
    if not disp:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado.")

    disp.estado = not disp.estado
    if not disp.estado:
        disp.desligar_em = None
    db.flush()

    dispositivos = db.query(Dispositivo).order_by(Dispositivo.bit_posicao.asc()).all()
    mascara = calcular_mascara_bits(dispositivos)
    acao = "ligar" if disp.estado else "desligar"

    historico = HistoricoComando(
        origem="web_manual",
        texto_transcrito=f"[Painel] {acao} {disp.nome}",
        comando_valido=True,
        acao_interpretada=acao,
        dispositivo_id=disp.id,
        mascara_bits_resultante=mascara,
        mensagem_retorno=f"'{disp.nome}' alterado manualmente para {'LIGADO' if disp.estado else 'DESLIGADO'}.",
    )
    db.add(historico)
    db.commit()
    elapsed_ms = round((time.perf_counter() - inicio) * 1000, 1)

    return {
        "valid": True,
        "action": acao,
        "target_name": disp.nome,
        "message": historico.mensagem_retorno,
        "processing_time_ms": elapsed_ms,
        "bitmask": mascara,
        "binary": formatar_binario(mascara),
        "hex": f"0x{mascara:02X}",
        "devices": [serializar_dispositivo(d) for d in dispositivos],
    }


@app.post("/api/devices/{device_id}/timer")
def definir_timer_dispositivo(
    device_id: int, payload: TimerRequest, db: Session = Depends(get_db)
):
    inicio = time.perf_counter()
    disp = db.query(Dispositivo).filter(Dispositivo.id == device_id).first()
    if not disp:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado.")

    duracao = max(0, min(payload.duration_seconds, 86400))
    if duracao > 0:
        disp.estado = True
        disp.desligar_em = datetime.now(timezone.utc) + timedelta(seconds=duracao)
        if duracao >= 3600:
            rotulo = f"{duracao // 3600}h"
        elif duracao >= 60:
            rotulo = f"{duracao // 60} min"
        else:
            rotulo = f"{duracao}s"
        msg = f"Timer definido em '{disp.nome}': desligará em {rotulo}."
    else:
        disp.desligar_em = None
        msg = f"Timer de '{disp.nome}' cancelado."

    db.flush()
    dispositivos = db.query(Dispositivo).order_by(Dispositivo.bit_posicao.asc()).all()
    mascara = calcular_mascara_bits(dispositivos)

    historico = HistoricoComando(
        origem="web_manual",
        texto_transcrito=f"[Painel] Timer {disp.nome} ({duracao}s)",
        comando_valido=True,
        acao_interpretada="timer",
        dispositivo_id=disp.id,
        mascara_bits_resultante=mascara,
        mensagem_retorno=msg,
    )
    db.add(historico)
    db.commit()
    elapsed_ms = round((time.perf_counter() - inicio) * 1000, 1)

    return {
        "valid": True,
        "action": "timer",
        "target_name": disp.nome,
        "message": msg,
        "processing_time_ms": elapsed_ms,
        "bitmask": mascara,
        "binary": formatar_binario(mascara),
        "hex": f"0x{mascara:02X}",
        "devices": [serializar_dispositivo(d) for d in dispositivos],
    }


@app.get("/api/history")
def listar_historico(limit: int = 20, db: Session = Depends(get_db)):
    registros = (
        db.query(HistoricoComando)
        .order_by(HistoricoComando.id.desc())
        .limit(min(limit, 100))
        .all()
    )
    return [
        {
            "id": r.id,
            "origem": r.origem,
            "texto_transcrito": r.texto_transcrito,
            "comando_valido": r.comando_valido,
            "acao_interpretada": r.acao_interpretada,
            "mascara_bits_resultante": r.mascara_bits_resultante,
            "binario": formatar_binario(r.mascara_bits_resultante),
            "mensagem_retorno": r.mensagem_retorno,
            "criado_em": r.criado_em.isoformat() if r.criado_em else None,
        }
        for r in registros
    ]
