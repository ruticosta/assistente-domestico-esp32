import os
import subprocess
import tempfile
import speech_recognition as sr


class ErroTranscricao(Exception):
    pass


def transcrever_audio_bytes(audio_bytes: bytes, extensao_origem: str = ".webm") -> str:
    """
    Converte o áudio recebido (webm/ogg/mp4/wav) para WAV PCM 16kHz mono via ffmpeg
    e executa Speech-to-Text em Português do Brasil (pt-BR).
    """
    if not audio_bytes:
        raise ErroTranscricao("Arquivo de áudio vazio.")

    ext = extensao_origem if extensao_origem.startswith(".") else f".{extensao_origem}"
    with tempfile.TemporaryDirectory() as tmpdir:
        caminho_entrada = os.path.join(tmpdir, f"input{ext}")
        caminho_wav = os.path.join(tmpdir, "output.wav")

        with open(caminho_entrada, "wb") as f:
            f.write(audio_bytes)

        # Converte para WAV 16kHz mono 16-bit PCM
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            caminho_entrada,
            "-ar",
            "16000",
            "-ac",
            "1",
            "-sample_fmt",
            "s16",
            caminho_wav,
        ]
        resultado = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if resultado.returncode != 0 or not os.path.exists(caminho_wav):
            raise ErroTranscricao("Não foi possível decodificar o áudio recebido.")

        recognizer = sr.Recognizer()
        with sr.AudioFile(caminho_wav) as source:
            audio_data = recognizer.record(source)

        try:
            texto = recognizer.recognize_google(audio_data, language="pt-BR")
            return texto.strip()
        except sr.UnknownValueError:
            raise ErroTranscricao("Não foi possível entender a fala no áudio. Tente falar mais perto do microfone.")
        except sr.RequestError as e:
            raise ErroTranscricao(f"Falha no serviço de reconhecimento de voz: {e}")
