from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from .database import Base


class Dispositivo(Base):
    __tablename__ = "dispositivos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    localizacao = Column(String(100), nullable=False)
    apelidos = Column(Text, nullable=False)
    bit_posicao = Column(SmallInteger, nullable=False, unique=True)
    estado = Column(Boolean, nullable=False, default=False)
    temperatura = Column(SmallInteger, nullable=False, default=22)
    desligar_em = Column(DateTime(timezone=True), nullable=True)
    atualizado_em = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    comandos = relationship("HistoricoComando", back_populates="dispositivo")


class HistoricoComando(Base):
    __tablename__ = "historico_comandos"

    id = Column(Integer, primary_key=True, index=True)
    origem = Column(String(30), nullable=False, default="web_voz")
    texto_transcrito = Column(Text, nullable=False)
    comando_valido = Column(Boolean, nullable=False)
    acao_interpretada = Column(String(50), nullable=True)
    dispositivo_id = Column(Integer, ForeignKey("dispositivos.id", ondelete="SET NULL"), nullable=True)
    mascara_bits_resultante = Column(SmallInteger, nullable=False, default=0)
    mensagem_retorno = Column(Text, nullable=False)
    criado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    dispositivo = relationship("Dispositivo", back_populates="comandos")
