---
id: T14
title: Escritor da planilha orientado ao schema (idempotente)
branch: feature/T14-schema-writer
depends_on: T06, T10, T11
acceptance: tests/acceptance/test_t14_schema_writer.py
allowed_paths:
  - app/sheets.py
---
## Contexto

Arquitetura v2 (#23, decisão D3: **escrita determinística em código**, sem LLM/MCP).
`PagamentoSheetWriter` (em `app/sheets.py`, ao lado do `SheetsRepository` da T06, que deve
continuar funcionando) grava um `Pagamento` (T10) no formato do `SheetSchema` (T11).

## Requisitos

- `__init__(worksheet, schema)`: o schema **precisa** ter uma coluna com `campo: id`; senão
  `SheetsError` (a idempotência depende dela). Guarda `self.worksheet` e `self.schema`.
- `from_service_account(file, sheet_id, schema)`: `gspread.service_account(filename=file)`
  → `open_by_key(sheet_id)` → `worksheet(schema.aba)`; em `WorksheetNotFound` cria com
  `add_worksheet(title=schema.aba, rows=1000, cols=len(schema.colunas))`. Erros → `SheetsError`.
- `ensure_header()`: `row_values(1)` vazio → `insert_row(schema.header(), index=1)`; senão
  `schema.validate_header(row)`; `SchemaError` → `SheetsError` (mensagem preservada).
- `append_pagamento(pagamento, usuario, registrado_em, id_gasto) -> bool`:
  1. Na primeira chamada da instância: `ensure_header()` e carga dos ids existentes com
     `col_values(<posição 1-based da coluna id>)` (sem o cabeçalho) — feito **uma vez**.
  2. `id_gasto` já existente (na planilha ou gravado por esta instância) → retorna `False`
     sem gravar.
  3. Linha = `schema.to_row(pagamento, {"id": id_gasto, "usuario": usuario,
     "registrado_em": registrado_em})`, com o mesmo escape de fórmulas da T06 aplicado
     (`= + - @` → prefixo `'`); `SchemaError` → `SheetsError`.
  4. `append_row(linha, value_input_option="USER_ENTERED")`; registra o id; retorna `True`.
- Qualquer exceção do worksheet/gspread → `SheetsError` encadeada (sem re-embrulhar
  `SheetsError`).

## Subtarefas (uma por sessão)

1. `__init__`, `ensure_header` e `append_pagamento` sem idempotência.
2. Idempotência por `id_gasto`.
3. `from_service_account`.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T14 python -m pytest tests/acceptance/test_t14_schema_writer.py` passa 100%.
- Testes da T06 continuam passando. `python -m pytest` e `ruff` limpos.
- Somente `app/sheets.py` (+ `tests/unit/`).

## Fora de escopo

Formatação visual; edição/remoção de linhas.
