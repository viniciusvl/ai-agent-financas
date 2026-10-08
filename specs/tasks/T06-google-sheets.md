---
id: T06
title: Repositório do Google Sheets
branch: feature/T06-google-sheets
depends_on: T01
acceptance: tests/acceptance/test_t06_sheets.py
allowed_paths:
  - app/sheets.py
---
## Contexto

`app/sheets.py` grava gastos confirmados em uma aba da planilha usando `gspread` com uma
service account do Google. A API é síncrona (o bot a chama via `asyncio.to_thread`).

## Requisitos

- `from_service_account(file, sheet_id, worksheet_name)`:
  `gspread.service_account(filename=file).open_by_key(sheet_id)`; obtém
  `spreadsheet.worksheet(worksheet_name)`; em `gspread.exceptions.WorksheetNotFound` cria
  com `add_worksheet(title=worksheet_name, rows=1000, cols=len(SHEET_HEADER))`.
  Chame `gspread.service_account` como atributo do módulo (`gspread.service_account(...)`),
  para permitir monkeypatch.
- `ensure_header()`: lê `row_values(1)`; vazio → `insert_row(SHEET_HEADER, index=1)`;
  igual a `SHEET_HEADER` → nada; diferente → `SheetsError`.
- `append_expense(expense, user, recorded_at)`: na primeira chamada da instância executa
  `ensure_header()` (memoriza o sucesso — só lê o cabeçalho uma vez); depois
  `append_row(to_sheet_row(...), value_input_option="USER_ENTERED")`.
- Qualquer exceção do worksheet/gspread → `SheetsError` (encadeada); `SheetsError`
  já levantada não deve ser re-embrulhada.

## Subtarefas (uma por sessão)

1. `ensure_header` e `append_expense` com cache do cabeçalho e tratamento de erros.
2. `from_service_account` (incluindo criação da aba).

## Critérios de aceite

- `ACCEPTANCE_TASKS=T06 python -m pytest tests/acceptance/test_t06_sheets.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente `app/sheets.py` (+ `tests/unit/`).

## Fora de escopo

Leitura de gastos, relatórios, totais.
