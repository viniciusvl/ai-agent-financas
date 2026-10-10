---
id: T01
title: Modelo de domínio Expense, normalização e formatação
branch: feature/T01-domain-model
depends_on:
acceptance: tests/acceptance/test_t01_domain.py
allowed_paths:
  - app/domain.py
---
## Contexto

`app/domain.py` define o gasto (`Expense`) usado por todos os outros módulos. As enums,
`SHEET_HEADER` e os campos do modelo já existem; faltam as regras de validação/normalização
e as funções de formatação. Leia `specs/000-produto.md`.

## Requisitos

### Validação/normalização do `Expense` (pydantic v2, `field_validator(mode="before")`)

- **amount**: aceita `Decimal`, `int`, `float` ou `str`.
  - Strings: remover espaços; se contiver vírgula, tratar `.` como separador de milhar e `,`
    como decimal (`"1.234,56"` → `1234.56`, `"35,50"` → `35.50`).
  - `float` deve ser convertido via `str()` (evitar `Decimal(19.99)` impreciso).
  - Quantizar para 2 casas com `ROUND_HALF_UP` (`"12.345"` → `12.35`).
  - Deve ser `> 0`; valores inválidos/vazios/zero/negativos → `ValidationError`.
- **currency**: case-insensitive, ignorando espaços e acentos. `None` → `BRL`.
  Aliases: BRL = `brl, r$, real, reais`; EUR = `eur, €, euro, euros`;
  USD = `usd, us$, $, dolar, dolares, dólar, dólares`. Qualquer outro → `ValidationError`.
- **category**: case-insensitive e sem acento (`"alimentacao"` → `alimentação`);
  desconhecido ou `None` → `outros`.
- **payment_method**: case-insensitive e sem acento (`"cartao"` → `cartão`);
  desconhecido ou `None` → `outro`.
- **description**: `strip()`; vazio ou > 200 caracteres → `ValidationError`.
- `Expense.model_validate_json(e.model_dump_json()) == e` deve continuar valendo.

### `format_confirmation(expense) -> str`

HTML do Telegram, exatamente (descrição com `html.escape`):

```
📝 <b>Confirme o gasto:</b>
• Valor: 35.50 BRL
• Categoria: alimentação
• Descrição: almoço
• Pagamento: dinheiro
• Data: 08/10/2026
```

### `to_sheet_row(expense, user, recorded_at) -> list`

Na ordem de `SHEET_HEADER`: data ISO (`"2026-10-08"`), descrição, categoria (valor da enum),
**valor como `float`**, moeda, pagamento, usuário, `recorded_at.isoformat()`, `raw_text`.

## Subtarefas (uma por sessão)

1. Validators de `amount` e `description`.
2. Validators de `currency`, `category` e `payment_method` (helper de normalização sem acento).
3. `format_confirmation` e `to_sheet_row`.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T01 python -m pytest tests/acceptance/test_t01_domain.py` passa 100%.
- `python -m pytest` passa (sem regressões) e `ruff check` / `ruff format --check` limpos.
- Somente `app/domain.py` (e testes novos em `tests/unit/`) alterados.

## Fora de escopo

Conversão de moedas, qualquer I/O.
