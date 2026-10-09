---
id: T10
title: Modelo de pagamento v2 e cálculo determinístico de parcelas
branch: feature/T10-payment-model
depends_on: T01
acceptance: tests/acceptance/test_t10_payment.py
allowed_paths:
  - app/payment.py
---
## Contexto

Arquitetura v2 (#23). `app/payment.py` define `Pagamento`, o modelo da escrita, e o cálculo de
parcelas. **O LLM nunca calcula `valor_parcela`** — a aplicação calcula. Reaproveite as regras
de `app/domain.py` (T01) importando o que precisar (`Currency`, `Category`, e os helpers de
normalização/valor); não altere `app/domain.py`.

## Requisitos

### `calcular_parcelas(valor_compra, quant_parcelas) -> list[Decimal]`
- `quant_parcelas` entre 1 e `MAX_PARCELAS` (24), senão `ValueError`; `valor_compra > 0`.
- Parcela base = `valor_compra / n` arredondada **para baixo** em centavos; a **primeira**
  parcela recebe a diferença, de modo que a soma seja **exatamente** `valor_compra`.
  - 100,00 em 3 → `[33.34, 33.33, 33.33]`; 10,00 em 4 → `[2.50]*4`; 0,05 em 2 → `[0.03, 0.02]`.
- Todas as parcelas com 2 casas decimais.

### `MetodoPagamento` — normalização (case-insensitive, sem acento, espaços/hífens/underscores tratados como iguais)
| Entrada (exemplos) | Resultado |
|---|---|
| `dinheiro`, `cash`, `especie`, `espécie` | `dinheiro` |
| `debito`, `débito`, `cartao de debito` | `debito` |
| `credito`, `crédito`, `cartao`, `cartao de credito`, `credito a vista`, `credito_a_vista` | `credito_a_vista` |
| `parcelado`, `credito parcelado`, `credito_parcelado` | `credito_parcelado` |
| `pix` | `pix` |
| `alipay`, `zhifubao` | `alipay` |
| `wechat`, `wechat pay`, `wechatpay`, `wechat_pay`, `weixin` | `wechat_pay` |
| qualquer outro, `None` | `outro` |

### `Pagamento`
- `valor_compra`: mesmas regras de `Expense.amount` (Decimal/int/float/str pt-BR, 2 casas
  ROUND_HALF_UP, > 0).
- `descricao`: mesmas regras de `Expense.description` (str, strip, 1–200).
- `moeda`/`categoria`: mesmas normalizações de `Expense.currency`/`Expense.category`
  (`None` → CNY / outros).
- `quant_parcelas`: `None` → 1. Regras (model validator, depois dos campos):
  1. `credito_a_vista` com `quant_parcelas >= 2` → vira `credito_parcelado`.
  2. `credito_parcelado` exige `2 <= quant_parcelas <= 24`, senão `ValidationError`.
  3. qualquer outro método → `quant_parcelas` forçado para 1.
- `extra="ignore"`: um `valor_parcela` vindo de fora é **ignorado**.
- Propriedades: `parcelas` (= `calcular_parcelas(valor_compra, quant_parcelas)`),
  `valor_parcela` (última parcela), `valor_primeira_parcela` (primeira).
- `Pagamento.model_validate_json(p.model_dump_json()) == p`.

## Subtarefas (uma por sessão)

1. `calcular_parcelas`.
2. Normalização de `MetodoPagamento` (função `normalizar_metodo` + validator).
3. Validators de `Pagamento` (valor, descrição, moeda, categoria, regras de parcelas) e propriedades.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T10 python -m pytest tests/acceptance/test_t10_payment.py` passa 100%.
- `python -m pytest` passa e `ruff check`/`ruff format --check` limpos.
- Somente `app/payment.py` (+ `tests/unit/`).

## Fora de escopo

Juros, IOF, conversão de moeda.
