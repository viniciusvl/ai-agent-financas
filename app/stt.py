"""Transcrição de áudio (speech-to-text) via Whisper em endpoint compatível com a OpenAI.

Spec: specs/tasks/T03-whisper-stt.md
"""

from typing import Any


class TranscriptionError(Exception):
    """Falha ao transcrever o áudio (erro da API ou transcrição vazia)."""


class WhisperTranscriber:
    def __init__(
        self,
        api_key: str,
        model: str = "whisper-1",
        language: str = "pt",
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        # `client` permite injetar um fake nos testes; em produção, openai.AsyncOpenAI.
        raise NotImplementedError("T03")

    async def transcribe(self, audio: bytes, filename: str = "audio.ogg") -> str:
        raise NotImplementedError("T03")
