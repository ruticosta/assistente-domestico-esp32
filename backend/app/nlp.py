import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional

from .models import Dispositivo


def normalizar_texto(texto: str) -> str:
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


PALAVRAS_LIGAR = (
    "ligar",
    "liga",
    "ligue",
    "acender",
    "acende",
    "acenda",
    "ativar",
    "ativa",
    "ative",
    "habilitar",
    "on",
)

PALAVRAS_DESLIGAR = (
    "desligar",
    "desliga",
    "desligue",
    "apagar",
    "apaga",
    "apague",
    "desativar",
    "desativa",
    "desative",
    "desabilitar",
    "off",
)

PALAVRAS_ALTERNAR = (
    "alternar",
    "alterna",
    "inverter",
    "inverte",
    "trocar",
    "troca",
    "mudar",
    "toggle",
)

PALAVRAS_TODOS = (
    "tudo",
    "todos",
    "todas",
    "geral",
    "casa inteira",
    "todas as luzes",
)

PALAVRAS_TEMP_MINIMA = (
    "temperatura minima",
    "minima",
    "minimo",
    "mais frio",
    "frio maximo",
    "gelar",
    "turbo",
)

PALAVRAS_TEMP_AMBIENTE = (
    "temperatura ambiente",
    "ambiente",
    "confortavel",
    "normal",
    "eco",
)

PALAVRAS_TEMP_MAXIMA = (
    "temperatura maxima",
    "maxima",
    "maximo",
    "mais quente",
)

PALAVRAS_AUMENTAR_TEMP = (
    "aumentar temperatura",
    "aumenta temperatura",
    "aumentar a temperatura",
    "subir temperatura",
    "subir a temperatura",
    "mais calor",
)

PALAVRAS_DIMINUIR_TEMP = (
    "diminuir temperatura",
    "diminui temperatura",
    "diminuir a temperatura",
    "baixar temperatura",
    "baixar a temperatura",
    "abaixar temperatura",
    "abaixar a temperatura",
)


@dataclass
class ResultadoInterpretacao:
    valido: bool
    acao: Optional[str]  # "ligar" | "desligar" | "alternar" | "temperatura" | "timer"
    alvo_todos: bool
    dispositivo: Optional[Dispositivo]
    mensagem: str
    temperatura_alvo: Optional[int] = None
    delta_temperatura: Optional[int] = None
    duracao_segundos: Optional[int] = None


def _contem_palavra(texto: str, candidatos: tuple[str, ...]) -> bool:
    for palavra in candidatos:
        if re.search(rf"\b{re.escape(palavra)}\b", texto):
            return True
    return False


def _encontrar_ar_condicionado(dispositivos: List[Dispositivo]) -> Optional[Dispositivo]:
    for d in dispositivos:
        if d.bit_posicao == 3 or "condicionado" in normalizar_texto(d.nome):
            return d
    return None


def _extrair_temperatura_numerica(texto: str) -> Optional[int]:
    # Ex: "colocar ar em 20 graus", "temperatura 18", "ar no 23"
    match = re.search(r"\b(1[6-9]|2[0-9]|30)\s*(?:graus|grau|c)?\b", texto)
    if match:
        return int(match.group(1))
    return None


def _extrair_duracao_segundos(texto: str) -> Optional[tuple[int, str]]:
    # Ex: "por 10 segundos", "em 30 minutos", "por 2 horas", "timer de 1 minuto"
    match = re.search(
        r"\b(\d+)\s*(segundos?|seg|s|minutos?|min|horas?|hora|h)\b",
        texto,
    )
    if not match:
        return None
    valor = int(match.group(1))
    unidade = match.group(2)
    if valor <= 0:
        return None
    if unidade.startswith("h"):
        segundos = min(valor * 3600, 86400)
        rotulo = f"{valor} hora" if valor == 1 else f"{valor} horas"
    elif unidade.startswith("m"):
        segundos = min(valor * 60, 86400)
        rotulo = f"{valor} minuto" if valor == 1 else f"{valor} minutos"
    else:
        segundos = min(valor, 86400)
        rotulo = f"{valor} segundo" if valor == 1 else f"{valor} segundos"
    return segundos, rotulo


def interpretar_comando(texto_bruto: str, dispositivos: List[Dispositivo]) -> ResultadoInterpretacao:
    texto = normalizar_texto(texto_bruto)
    if not texto:
        return ResultadoInterpretacao(
            valido=False,
            acao=None,
            alvo_todos=False,
            dispositivo=None,
            mensagem="Comando vazio. Fale ou digite uma instrução.",
        )

    # 1) Verifica primeiro comandos específicos do Ar-Condicionado (timer e temperatura)
    ac = _encontrar_ar_condicionado(dispositivos)
    if ac is not None:
        duracao = _extrair_duracao_segundos(texto)
        if duracao is not None:
            segundos, rotulo = duracao
            return ResultadoInterpretacao(
                valido=True,
                acao="timer",
                alvo_todos=False,
                dispositivo=ac,
                duracao_segundos=segundos,
                mensagem=f"Ar-Condicionado ligado com timer de {rotulo}.",
            )

        if "cancelar timer" in texto or "remover timer" in texto or "sem timer" in texto:
            return ResultadoInterpretacao(
                valido=True,
                acao="timer",
                alvo_todos=False,
                dispositivo=ac,
                duracao_segundos=0,
                mensagem="Timer do Ar-Condicionado cancelado.",
            )

        menciona_ac_ou_temp = (
            "temperatura" in texto
            or "graus" in texto
            or "grau" in texto
            or "ar condicionado" in texto
            or _contem_palavra(texto, ("ar", "clima", "climatizador"))
        )

        if _contem_palavra(texto, PALAVRAS_TEMP_MINIMA):
            return ResultadoInterpretacao(
                valido=True,
                acao="temperatura",
                alvo_todos=False,
                dispositivo=ac,
                temperatura_alvo=16,
                mensagem="Ar-Condicionado ajustado para temperatura mínima (16°C).",
            )

        if _contem_palavra(texto, PALAVRAS_TEMP_AMBIENTE):
            return ResultadoInterpretacao(
                valido=True,
                acao="temperatura",
                alvo_todos=False,
                dispositivo=ac,
                temperatura_alvo=24,
                mensagem="Ar-Condicionado ajustado para temperatura ambiente (24°C).",
            )

        if _contem_palavra(texto, PALAVRAS_TEMP_MAXIMA):
            return ResultadoInterpretacao(
                valido=True,
                acao="temperatura",
                alvo_todos=False,
                dispositivo=ac,
                temperatura_alvo=28,
                mensagem="Ar-Condicionado ajustado para temperatura máxima (28°C).",
            )

        if _contem_palavra(texto, PALAVRAS_AUMENTAR_TEMP):
            return ResultadoInterpretacao(
                valido=True,
                acao="temperatura",
                alvo_todos=False,
                dispositivo=ac,
                delta_temperatura=2,
                mensagem="Temperatura do Ar-Condicionado aumentada em +2°C.",
            )

        if _contem_palavra(texto, PALAVRAS_DIMINUIR_TEMP):
            return ResultadoInterpretacao(
                valido=True,
                acao="temperatura",
                alvo_todos=False,
                dispositivo=ac,
                delta_temperatura=-2,
                mensagem="Temperatura do Ar-Condicionado reduzida em -2°C.",
            )

        if menciona_ac_ou_temp:
            temp_num = _extrair_temperatura_numerica(texto)
            if temp_num is not None:
                return ResultadoInterpretacao(
                    valido=True,
                    acao="temperatura",
                    alvo_todos=False,
                    dispositivo=ac,
                    temperatura_alvo=temp_num,
                    mensagem=f"Ar-Condicionado ajustado para {temp_num}°C.",
                )

    # 2) Comandos gerais de ligar / desligar / alternar
    acao: Optional[str] = None
    if _contem_palavra(texto, PALAVRAS_DESLIGAR):
        acao = "desligar"
    elif _contem_palavra(texto, PALAVRAS_LIGAR):
        acao = "ligar"
    elif _contem_palavra(texto, PALAVRAS_ALTERNAR):
        acao = "alternar"

    if not acao:
        return ResultadoInterpretacao(
            valido=False,
            acao=None,
            alvo_todos=False,
            dispositivo=None,
            mensagem=f"Ação não reconhecida em: '{texto_bruto}'. Use 'ligar', 'desligar', 'alternar' ou ajuste de temperatura.",
        )

    if _contem_palavra(texto, PALAVRAS_TODOS):
        return ResultadoInterpretacao(
            valido=True,
            acao=acao,
            alvo_todos=True,
            dispositivo=None,
            mensagem=f"Ação '{acao}' aplicada a todos os dispositivos.",
        )

    # Busca o dispositivo cujo apelido mais específico apareça no comando
    melhor_match: Optional[Dispositivo] = None
    melhor_tamanho = 0

    for disp in dispositivos:
        termos = [normalizar_texto(disp.nome)]
        termos.extend(normalizar_texto(a) for a in disp.apelidos.split(",") if a.strip())
        for termo in termos:
            if termo and re.search(rf"\b{re.escape(termo)}\b", texto):
                if len(termo) > melhor_tamanho:
                    melhor_tamanho = len(termo)
                    melhor_match = disp

    if not melhor_match:
        nomes_disponiveis = ", ".join(d.nome for d in dispositivos)
        return ResultadoInterpretacao(
            valido=False,
            acao=acao,
            alvo_todos=False,
            dispositivo=None,
            mensagem=f"Dispositivo não identificado em '{texto_bruto}'. Disponíveis: {nomes_disponiveis}.",
        )

    return ResultadoInterpretacao(
        valido=True,
        acao=acao,
        alvo_todos=False,
        dispositivo=melhor_match,
        mensagem=f"Comando '{acao}' executado em '{melhor_match.nome}' (bit {melhor_match.bit_posicao}).",
    )
