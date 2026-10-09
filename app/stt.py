"""Transcrição de áudio (speech-to-text) via Whisper em endpoint compatível com a OpenAI.

Spec: specs/tasks/T03-whisper-stt.md
"""

from typing import Any

from openai import AsyncOpenAI


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
        self.model = model
        self.language = language
        if client is not None:
            self.client = client
        elif base_url is not None:
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = AsyncOpenAI(api_key=api_key)

    async def transcribe(self, audio: bytes, filename: str = "audio.ogg") -> str:
        raise NotImplementedError("T03")
