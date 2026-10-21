---
id: T20
title: Bot — toque duplo em Confirmar não mostra "expirou"
branch: feature/T20-confirmacao-duplicada
depends_on: T16
acceptance: tests/acceptance/test_t20_confirmacao_duplicada.py
allowed_paths:
  - app/bot.py
---
## Contexto

Issue #44. Dois toques rápidos em **✅ Confirmar** geram dois callbacks. A gravação já é
idempotente, mas o segundo callback encontra o pendente removido e troca a mensagem
"✅ Gasto registrado!" por `MSG_EXPIRED`.

## Requisitos (`app/bot.py`, `BotService`)

- Guardar em memória os ids confirmados com sucesso e o momento (`self.clock()`), por
  **10 minutos** (constante `CONFIRMADOS_TTL = timedelta(minutes=10)` no módulo).
- Callback `confirm:<id>` cujo pendente não existe mais:
  - id confirmado há no máximo 10 minutos → apenas
    `answer_callback_query(id, MSG_CALLBACK_SAVED)`; **não** edita a mensagem e não grava;
  - caso contrário → comportamento atual (`MSG_EXPIRED` na resposta e na mensagem).
- Remover da memória as entradas vencidas (ao consultar ou ao registrar), para não crescer
  sem limite.
- `cancel:` e os demais fluxos não mudam.

## Subtarefas (uma por sessão)

1. Memória de confirmados com TTL e o novo comportamento do callback.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T20 python -m pytest tests/acceptance/test_t20_confirmacao_duplicada.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente `app/bot.py` (+ `tests/unit/`).
