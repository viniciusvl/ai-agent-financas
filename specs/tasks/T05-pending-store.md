---
id: T05
title: Armazenamento de gastos pendentes em SQLite
branch: feature/T05-pending-store
depends_on: T01
acceptance: tests/acceptance/test_t05_pending_store.py
allowed_paths:
  - app/pending_store.py
---
## Contexto

Entre a extração e o clique em Confirmar, o gasto fica pendente. `app/pending_store.py`
persiste isso em SQLite (biblioteca padrão `sqlite3`) para sobreviver a reinícios.

## Requisitos

- `init()`: cria o diretório pai do `db_path` se não existir e a tabela
  `pending(id TEXT PRIMARY KEY, chat_id INTEGER, user_id INTEGER, expense_json TEXT,
  created_at REAL)`; idempotente.
- `save(chat_id, user_id, expense) -> str`: id = `uuid.uuid4().hex[:12]`; `created_at =
  clock()`; `expense_json = expense.model_dump_json()`.
- `get(id) -> PendingExpense | None`: `None` se não existir ou se
  `clock() - created_at > ttl_seconds` (exatamente no limite ainda é válido).
- `delete(id) -> bool`: `True` se removeu.
- `purge_expired() -> int`: remove expirados e retorna a quantidade.
- Abrir uma conexão por operação (`with sqlite3.connect(...)`) — seguro para threads.

## Subtarefas (uma por sessão)

1. `init`, `save`, `get` (sem TTL).
2. TTL em `get`, `delete`, `purge_expired`.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T05 python -m pytest tests/acceptance/test_t05_pending_store.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente `app/pending_store.py` (+ `tests/unit/`).

## Fora de escopo

ORM, migrações.
