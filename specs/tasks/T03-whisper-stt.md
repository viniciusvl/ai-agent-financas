---
id: T03
title: Transcrição de áudio com Whisper
branch: feature/T03-whisper-stt
depends_on: T01
acceptance: tests/acceptance/test_t03_stt.py
allowed_paths:
  - app/stt.py
---
## Contexto

`app/stt.py` transcreve os áudios do Telegram (voice notes `.oga`/opus e arquivos de áudio)
usando um endpoint compatível com a API de transcrição da OpenAI (OpenAI ou servidor
Whisper self-hosted).

## Requisitos

- `__init__(api_key, model="whisper-1", language="pt", base_url=None, client=None)`:
  guarda `self.model`, `self.language` e `self.client`. Se `client` for `None`, usar
  `openai.AsyncOpenAI(api_key=api_key, base_url=base_url)` (sem `base_url` quando `None`).
- `transcribe(audio, filename="audio.ogg") -> str`:
  - `audio` vazio → `TranscriptionError` sem chamar a API;
  - extensão `.oga` é trocada por `.ogg` (a API rejeita `.oga`);
  - chama `await client.audio.transcriptions.create(model=..., file=(filename, audio),
    language=..., response_format="text")`;
  - o retorno pode ser `str` ou objeto com atributo `.text`; devolver `strip()`;
  - resultado vazio → `TranscriptionError`;
  - qualquer exceção da API → `TranscriptionError` (encadeada com `from`).

## Subtarefas (uma por sessão)

1. `__init__` com client padrão e injeção.
2. `transcribe` com todas as regras.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T03 python -m pytest tests/acceptance/test_t03_stt.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente `app/stt.py` (+ `tests/unit/`).

## Fora de escopo

Conversão de formato com ffmpeg, Whisper local embutido.
