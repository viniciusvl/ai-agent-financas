---
id: T02
title: Cliente assíncrono da Bot API do Telegram
branch: feature/T02-telegram-client
depends_on: T01
acceptance: tests/acceptance/test_t02_telegram.py
allowed_paths:
  - app/telegram_api.py
---
## Contexto

`app/telegram_api.py` encapsula as chamadas HTTP à Bot API usando `httpx.AsyncClient`.
As assinaturas já existem; implemente os corpos.

## Requisitos

- Todas as chamadas: `POST {base_url}/bot{token}/{método}` com corpo JSON. Helper privado
  `_call(method, payload) -> Any` que retorna `response.json()["result"]`.
- Erros → `TelegramError`:
  - resposta JSON com `ok: false` (qualquer status HTTP) → mensagem contém `description`;
  - erro de rede (`httpx.HTTPError`) ou resposta não-JSON.
- Se `http` não for injetado, criar `httpx.AsyncClient(timeout=30)` próprio; `aclose()` fecha
  apenas o client criado internamente.
- `send_message(chat_id, text, reply_markup=None)` → payload
  `{"chat_id", "text", "parse_mode": "HTML"}` + `reply_markup` **somente se** informado.
- `edit_message_text(chat_id, message_id, text, reply_markup=None)` → mesmo padrão.
- `answer_callback_query(callback_query_id, text=None)` → `{"callback_query_id"}` + `text`
  se informado; retorna `True`.
- `download_file(file_id)` → `getFile` com `{"file_id"}`, depois
  `GET {base_url}/file/bot{token}/{file_path}`; status ≠ 2xx → `TelegramError`.
- `set_webhook(url, secret_token)` → `{"url", "secret_token",
  "allowed_updates": ["message", "callback_query"], "drop_pending_updates": false}`.
- `confirmation_keyboard(pending_id)` → teclado inline com uma linha:
  `✅ Confirmar` (`confirm:<id>`) e `❌ Cancelar` (`cancel:<id>`).
- Nunca logar o token.

## Subtarefas (uma por sessão)

1. `__init__`, `aclose`, `_call` com tratamento de erros, `confirmation_keyboard`.
2. `send_message`, `edit_message_text`, `answer_callback_query`, `set_webhook`.
3. `download_file`.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T02 python -m pytest tests/acceptance/test_t02_telegram.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente `app/telegram_api.py` (+ `tests/unit/`).

## Fora de escopo

Polling, outros métodos da Bot API, retries.
