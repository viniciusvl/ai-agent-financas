---
id: T16
title: Orquestração v2 do bot (roteador, escrita com confirmação, leitura)
branch: feature/T16-bot-flow-v2
depends_on: T02, T03, T05, T12, T13, T14, T15
acceptance: tests/acceptance/test_t16_bot_flow_v2.py
allowed_paths:
  - app/bot.py
  - app/pending_store.py
---
## Contexto

Arquitetura v2 (#23). Substitui a T07 (#8). `BotService` liga Telegram (T02) ↔ Whisper (T03)
↔ roteador Jev (T12) ↔ extrator (T13) / agente de leitura (T15) ↔ pendentes (T05) ↔ escritor
(T14). Colaboradores são injetados (duck typing); os testes usam fakes. Textos em
`app/messages.py` (não altere). `METODO_LABEL` já existe em `app/bot.py`.

## Requisitos

### `PendingStore` genérico (`app/pending_store.py`)
- Novo parâmetro `model: type[BaseModel] = Expense` no `__init__`. `save(chat_id, user_id,
  expense)` aceita qualquer instância de modelo pydantic (o nome do parâmetro continua
  `expense`); `get` desserializa com `self.model.model_validate_json`. Os testes da T05
  continuam passando sem mudança.

### Formatação
- `format_confirmacao(p)` — exatamente (descrição com `html.escape`, valores com
  `app.queries.format_valor`):
  ```
  📝 <b>Confirme o pagamento:</b>
  • Valor: R$ 3.000,00
  • Pagamento: crédito parcelado em 10x de R$ 300,00
  • Categoria: compras
  • Descrição: celular
  • Data: 08/10/2026 14:07
  ```
  - Linha "Pagamento": `METODO_LABEL[metodo]`; se parcelado: `"<label> em <n>x de <parcela>"`,
    e se a primeira parcela for diferente: `"<label> em <n>x (1ª de <primeira> + <n-1>x de
    <parcela>)"`.
  - Linha "Data": `dd/mm/aaaa` + (`" HH:MM"` se houver hora).
- `format_registrado(p)` = `MSG_SAVED_HEADER` + `"\n"` + as linhas de `format_confirmacao(p)`
  a partir da segunda.

### `BotService`
- `__init__(telegram, transcriber, router, extractor, read_agent, store, writer,
  allowed_user_ids, timezone, clock=None)`; `self.allowed_user_ids` é um `set`; `clock`
  padrão = `datetime.now(ZoneInfo(timezone))`.
- `handle_update` **nunca** propaga exceção (captura tudo + `logger.exception`).
- **Autorização** (mensagens e callbacks) igual à T07: fora da lista (lista vazia = ninguém) →
  `MSG_UNAUTHORIZED.format(user_id=...)` (callback: `answer_callback_query`) e nada mais.
- **Comandos** `/start`, `/help` (aceitar `@NomeDoBot`) → `MSG_HELP`.
- **Horário da mensagem** (`recebido_em`): `message.date` (unix, UTC) → `datetime` com fuso
  UTC; ausente → `clock()`.
- **Voz/áudio** igual à T07: `download_file`, nome `voice.ogg` ou `audio.file_name`
  (fallback `audio.ogg`), `transcribe`, envia `MSG_TRANSCRIPTION.format(text=html.escape(t))`,
  segue com o texto transcrito; erro no download/transcrição → `MSG_TRANSCRIPTION_FAILED`.
- **Roteamento**: `rota = await router.route(texto)`; `RouterError` → `MSG_ROUTER_FAILED`.
  - `escrita` → `res = await extractor.extract(texto, recebido_em)`:
    `ExtractionError` → `MSG_EXTRACTION_FAILED`; `res.erro` →
    `MSG_NOT_EXPENSE.format(reason=res.erro)`; `res.pergunta` → envia a pergunta;
    `res.pagamento` → `id = store.save(chat_id, user_id, pagamento)` e
    `send_message(chat_id, format_confirmacao(p), reply_markup=confirmation_keyboard(id))`.
  - `leitura` → `resposta = await read_agent.answer(texto, recebido_em)` e envia;
    `ReadError` → `MSG_LEITURA_FAILED`.
  - `outro` → `MSG_OUTRO`.
- **Callbacks** `confirm:<id>` / `cancel:<id>` (chat/message de `callback_query.message`):
  - pendente inexistente/expirado → `answer_callback_query(id, MSG_EXPIRED)` e
    `edit_message_text(..., MSG_EXPIRED)`;
  - `from.id` ≠ dono → `answer_callback_query(id, MSG_NOT_OWNER)`;
  - confirm → `await asyncio.to_thread(writer.append_pagamento, pagamento, user_name,
    clock(), pending_id)` (o id do pendente é o id do gasto → idempotência). Retorno `True`
    ou `False` (já gravado) = sucesso: `store.delete`, `edit_message_text(format_registrado(p))`,
    `answer_callback_query(id, MSG_CALLBACK_SAVED)`. `SheetsError` → mantém o pendente e
    `answer_callback_query(id, MSG_SAVE_FAILED)` (sem editar);
  - cancel → `store.delete`, `edit_message_text(MSG_CANCELLED)`,
    `answer_callback_query(id, MSG_CALLBACK_CANCELLED)`;
  - outro `data` → apenas `answer_callback_query(id)`.
- `user_name`: `first_name` + `" " + last_name`; senão `username`; senão o id.
- Outros updates (edited_message, sticker, sem mensagem) → ignorar.
- Log INFO por mensagem: intenção, origem e confiança da rota (sem conteúdo do texto).

## Subtarefas (uma por sessão)

1. `PendingStore` genérico + `format_confirmacao`/`format_registrado`.
2. Estrutura, autorização, comandos, `recebido_em`, voz.
3. Roteamento: escrita (extração/pergunta/confirmação), leitura e outro.
4. Callbacks e garantia de nunca propagar exceções.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T16 python -m pytest tests/acceptance/test_t16_bot_flow_v2.py` passa 100%.
- Testes da T05 continuam passando. `python -m pytest` e `ruff` limpos.
- Somente os caminhos permitidos (+ `tests/unit/`).

## Fora de escopo

Conversa de múltiplos turnos (responder à pergunta de valor reenviando a mensagem completa
é o fluxo esperado); edição de gastos gravados.
