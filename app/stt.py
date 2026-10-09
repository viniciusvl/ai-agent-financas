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
        """Transcreve o áudio e devolve o texto (já com `strip`)."""
        if not audio:
            raise TranscriptionError("áudio vazio")
        if filename.lower().endswith(".oga"):
            # A API de transcrição rejeita `.oga`; o mesmo conteúdo vale como `.ogg`.
            filename = filename[:-4] + ".ogg"
        try:
            result = await self.client.audio.transcriptions.create(
                model=self.model,
                file=(filename, audio),
                language=self.language,
                response_format="text",
            )
        except Exception as exc:  # noqa: BLE001 - qualquer erro da API vira TranscriptionError
            raise TranscriptionError("falha ao transcrever o áudio") from exc
        text = result if isinstance(result, str) else getattr(result, "text", "")
        text = text.strip() if isinstance(text, str) else ""
        if not text:
            raise TranscriptionError("transcrição vazia")
        return text
