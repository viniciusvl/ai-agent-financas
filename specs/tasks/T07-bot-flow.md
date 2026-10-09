---
id: T07
title: Orquestração do fluxo do bot (BotService)
branch: feature/T07-bot-flow
depends_on: T01, T02, T03, T04, T05, T06
acceptance: tests/acceptance/test_t07_bot_flow.py
allowed_paths:
  - app/bot.py
---
## Contexto

`app/bot.py` contém `BotService`, que recebe updates do Telegram e coordena
Telegram ↔ Whisper ↔ DeepSeek ↔ store ↔ Sheets. Todos os textos estão em
`app/messages.py` (use as constantes — não altere esse arquivo). Os colaboradores são
injetados (duck typing), então os testes usam fakes.

## Requisitos

- `__init__(telegram, transcriber, extractor, store, sheets, allowed_user_ids, timezone,
  clock=None)`: guarda tudo; `self.allowed_user_ids` é um `set` (mutável);
  `clock` padrão = `datetime.now(ZoneInfo(timezone))`.
- "Hoje" = `clock().astimezone(ZoneInfo(timezone)).date()`.
- `handle_update(update)` **nunca** propaga exceção (captura tudo e faz `logger.exception`).
- **Autorização** (mensagens e callbacks): `from.id` fora de `allowed_user_ids` (lista vazia
  = ninguém) → `send_message(chat_id, MSG_UNAUTHORIZED.format(user_id=...))` (para callback,
  `answer_callback_query`) e nada mais.
- **Mensagem de texto**:
  - `/start` ou `/help` (aceitar sufixo `@NomeDoBot`) → `MSG_HELP`;
  - senão → `extractor.extract(text, today)`; com `expense` → `store.save(chat_id, user_id,
    expense)` e `send_message(chat_id, format_confirmation(expense),
    reply_markup=confirmation_keyboard(id))`; com `error` →
    `MSG_NOT_EXPENSE.format(reason=error)`; `ExtractionError` → `MSG_EXTRACTION_FAILED`.
- **Voice/Audio**: `download_file(file_id)`; filename = `voice.ogg` para `voice` ou
  `audio.file_name` (fallback `audio.ogg`) para `audio`; `transcribe(bytes, filename=...)`;
  envia `MSG_TRANSCRIPTION.format(text=html.escape(texto))`; segue o fluxo de texto com o
  texto transcrito. `TranscriptionError` (ou erro no download) → `MSG_TRANSCRIPTION_FAILED`.
- **Callback** `confirm:<id>` / `cancel:<id>` (chat e message_id vêm de
  `callback_query.message`):
  - pendente inexistente/expirado → `answer_callback_query(id, MSG_EXPIRED)` e
    `edit_message_text(..., MSG_EXPIRED)`;
  - `from.id` ≠ `pending.user_id` → `answer_callback_query(id, MSG_NOT_OWNER)`;
  - confirm → `await asyncio.to_thread(sheets.append_expense, expense, user_name, clock())`;
    sucesso → `store.delete`, `edit_message_text` com `MSG_SAVED_HEADER` + linhas do resumo
    (o texto de `format_confirmation` sem a primeira linha) e
    `answer_callback_query(id, MSG_CALLBACK_SAVED)`; `SheetsError` → mantém o pendente e
    `answer_callback_query(id, MSG_SAVE_FAILED)` (sem editar);
  - cancel → `store.delete`, `edit_message_text(MSG_CANCELLED)`,
    `answer_callback_query(id, MSG_CALLBACK_CANCELLED)`;
  - outro `data` → apenas `answer_callback_query(id)`.
- `user_name`: `first_name` + `" " + last_name` (se houver); senão `username`; senão o id.
- Outros tipos de update (edited_message, sticker, sem mensagem...) → ignorar.

## Subtarefas (uma por sessão)

1. Estrutura, parsing do update, autorização e `/start`/`/help`.
2. Fluxo de texto (extração → pendente → confirmação) e erros.
3. Fluxo de voz/áudio.
4. Callbacks confirm/cancel e casos de erro; garantia de nunca propagar exceções.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T07 python -m pytest tests/acceptance/test_t07_bot_flow.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente `app/bot.py` (+ `tests/unit/`).

## Fora de escopo

Edição de campos do gasto por conversa, relatórios, multi-idioma.
