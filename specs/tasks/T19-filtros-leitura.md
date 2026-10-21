---
id: T19
title: Leitura — filtros por categoria e forma de pagamento no total do período
branch: feature/T19-filtros-leitura
depends_on: T15
acceptance: tests/acceptance/test_t19_filtros_leitura.py
allowed_paths:
  - app/queries.py
  - app/read_agent.py
---
## Contexto

Issue #42. Hoje "quanto gastei com alimentação?" escolhe `total_por_categoria` e responde com
todas as categorias. A ferramenta `total_periodo` passa a aceitar filtros opcionais. O prompt
de leitura (`app/prompts.py`) já orienta o modelo a usá-los — não o altere.

## Requisitos

### `app/queries.py`
- `total_periodo(registros, inicio, fim, categoria=None, metodo_pagamento=None)`: além do
  período inclusivo, considera só os registros com `categoria == categoria` e/ou
  `metodo_pagamento == metodo_pagamento` quando informados. Sem filtros, o comportamento atual
  não muda.

### `app/read_agent.py`
- `TOOLS`: a função `total_periodo` ganha as propriedades **opcionais** `categoria`
  (`"type": "string"`, `"enum"` = valores de `Category`, na ordem do enum) e
  `metodo_pagamento` (`"type": "string"`, `"enum"` = valores de `MetodoPagamento`, na ordem).
  `required` continua `["inicio", "fim"]`.
- Valor de filtro fora do enum → `MSG_LEITURA_NAO_SUPORTADA`.
- Resposta com filtros: `💰 Total de {inicio} a {fim} ({filtros}): {T}`, onde `{filtros}` junta,
  nesta ordem, `categoria <valor>` e `pagamento <valor>` com `", "`. Sem filtros, o formato
  atual não muda.

## Subtarefas (uma por sessão)

1. Filtros em `total_periodo` (queries).
2. `TOOLS`, validação e formatação no `ReadAgent`.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T19 python -m pytest tests/acceptance/test_t19_filtros_leitura.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente os caminhos permitidos (+ `tests/unit/`).
