---
id: T11
title: Schema da planilha como configuração versionada
branch: feature/T11-sheet-schema
depends_on: T10
acceptance: tests/acceptance/test_t11_sheet_schema.py
allowed_paths:
  - app/sheet_schema.py
---
## Contexto

Arquitetura v2 (#23). O formato padrão da planilha vive em `config/planilha.yaml`
(o orquestrador mantém o exemplo/padrão em `config/planilha.example.yaml`). O mesmo schema
alimenta o contexto dos prompts (o agente recebe o formato, não o descobre) e o escritor.
Use `yaml.safe_load` (pyyaml já está em `requirements.txt`).

## Formato do YAML

```yaml
aba: Gastos
colunas:
  - nome: Data            # texto do cabeçalho (único)
    campo: data           # CAMPOS_PAGAMENTO ou CAMPOS_EXTRAS
    tipo: data            # um de TIPOS
    formato: "%d/%m/%Y"   # opcional (strftime) — tipos data/hora/datahora
    obrigatoria: true     # opcional, padrão true
```

## Requisitos

- `SheetSchema.load(path)`: lê o arquivo (UTF-8) e delega a `from_dict`. Arquivo inexistente ou
  YAML inválido → `SchemaError`.
- `SheetSchema.from_dict(data)` valida e lança `SchemaError` cuja mensagem **contém o `nome` da
  coluna problemática** quando houver uma:
  - `aba` ausente/vazia; `colunas` ausente ou lista vazia;
  - coluna sem `nome`/`campo`/`tipo`; `nome` duplicado; `campo` fora de
    `CAMPOS_PAGAMENTO + CAMPOS_EXTRAS`; `tipo` fora de `TIPOS`.
- `header()` → nomes na ordem.
- `to_row(pagamento, extras)` → um valor por coluna, na ordem; valor do campo vem de
  `extras[campo]` para `CAMPOS_EXTRAS` e de `getattr(pagamento, campo)` para os demais:
  | tipo | saída |
  |---|---|
  | `texto` | `str(valor)`; `None` → `""` |
  | `data` | `strftime(formato or "%d/%m/%Y")` |
  | `hora` | `strftime(formato or "%H:%M")`; `None` → `""` |
  | `datahora` | `strftime(formato)` se houver formato, senão `isoformat()` |
  | `moeda` | `float(valor)` |
  | `inteiro` | `int(valor)` |
  | `enum` | `str(valor.value)` se for enum, senão `str(valor)` |
  - Coluna `obrigatoria` com valor `None` ou `""` → `SchemaError` com o nome da coluna.
  - Campo de `CAMPOS_EXTRAS` usado no schema mas ausente em `extras` → `SchemaError`.
- `prompt_context()` → texto começando com `Colunas da planilha (aba <aba>):` e uma linha por
  coluna no formato `- <nome>: campo <campo>, tipo <tipo>` (+ `, formato <formato>` se houver).
- `validate_header(header)` → se diferente de `header()`, `SchemaError` que menciona a primeira
  posição divergente (1-based) e o nome esperado nessa posição; cabeçalho maior/menor também é erro.

## Subtarefas (uma por sessão)

1. `from_dict`/`load` com todas as validações.
2. `header` e `to_row` com formatação por tipo.
3. `prompt_context` e `validate_header`.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T11 python -m pytest tests/acceptance/test_t11_sheet_schema.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente `app/sheet_schema.py` (+ `tests/unit/`).

## Fora de escopo

Formatação visual da planilha; leitura de linhas (T15).
