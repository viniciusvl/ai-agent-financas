---
id: T18
title: Generalização — remover especificidades de viagem/China
branch: feature/T18-generalizacao
depends_on: T01, T10, T15, T16, T17
acceptance: tests/acceptance/test_t18_generalizacao.py
allowed_paths:
  - app/domain.py
  - app/payment.py
  - app/bot.py
  - app/queries.py
  - app/payment_extractor.py
  - app/read_agent.py
  - app/extractor.py
  - app/main.py
  - app/sheets.py
  - app/stt.py
  - evals/casos.yaml
  - tools/run_evals.py
  - deploy/
  - docs/deploy.md
  - Dockerfile
  - docker-compose.yml
  - scripts/set_webhook.py
---
## Contexto

O projeto passou a se chamar **ai-agent-financas**: um agente de finanças pessoais **geral**,
que lê e grava gastos numa planilha específica do Google Sheets (o modelo da planilha é
definido pelo dono e descrito em `config/planilha.yaml`). Não há mais nada específico de
viagem ou da China. O orquestrador já atualizou prompts, textos, configuração, metadados,
specs e os testes de aceite antigos (agora neutros). Falta o código da aplicação, os casos de
avaliação e os artefatos de deploy.

## Requisitos

### Moedas (`app/domain.py`)
- `Currency` passa a ser **`BRL`, `USD`, `EUR`** (remover `CNY`).
- Aliases: BRL = `brl, r$, real, reais`; USD = `usd, us$, $, dolar, dolares, dólar, dólares`;
  EUR = `eur, €, euro, euros`. Qualquer outro (inclusive `cny`, `yuan`) → `ValidationError`.
- `None` → **`BRL`**; padrão do campo `Expense.currency` = `BRL`.

### Formas de pagamento
- v1 (`app/domain.py`, `PaymentMethod`): **`dinheiro`, `cartão`, `pix`, `outro`** (remover
  `alipay` e `wechat`); desconhecido → `outro`.
- v2 (`app/payment.py`, `MetodoPagamento`): **`dinheiro`, `debito`, `credito_a_vista`,
  `credito_parcelado`, `pix`, `boleto`, `transferencia`, `outro`** (remover `alipay`,
  `wechat_pay`). Novos aliases: `boleto`, `boleto bancário` → `boleto`; `transferência`,
  `transferencia bancaria`, `ted`, `doc` → `transferencia`. Remover aliases `zhifubao`,
  `weixin`, `wechat*`, `alipay` (passam a cair em `outro`).
- `Pagamento.moeda` padrão e `None` → **`BRL`**.
- `app/bot.py`: `METODO_LABEL` com exatamente os membros de `MetodoPagamento`
  (`boleto` → `"boleto"`, `transferencia` → `"transferência"`).

### Padrões de fuso e moeda
- Parâmetros padrão: `timezone="America/Sao_Paulo"` em `PaymentExtractor`, `ReadAgent` e
  `BotService`; `default_currency="BRL"` em `PaymentExtractor` e `ExpenseExtractor`.
- `app/queries.py`: `format_valor` com `EUR` → `"€ 1.234,56"` (remover o prefixo de `CNY`);
  `Registro.moeda` padrão `"BRL"`.

### Nome do projeto e deploy
- `app/main.py`: `FastAPI(title="ai-agent-financas")`.
- Nginx: renomear para `deploy/nginx/ai-agent-financas.conf` e
  `deploy/nginx/ai-agent-financas.http-only.conf`; atualizar `docs/deploy.md`, `Dockerfile`,
  `docker-compose.yml` e comentários (nome do projeto; nada de viagem/China).

### Avaliação (`evals/casos.yaml`, `tools/run_evals.py`)
- Reescrever os casos como **gastos pessoais gerais no Brasil** (mercado, uber, aluguel, conta
  de luz, farmácia, streaming, compras parceladas…), mantendo ≥ 60 casos e as mesmas
  proporções de rotas. Cobertura: cada `MetodoPagamento` ≥ 2; cada `Currency` ≥ 3; a moeda
  mais frequente (BRL) ≥ 10; ≥ 6 parcelados com ≥ 4 quantidades distintas.
- `verificar_cobertura` deve derivar métodos e moedas de `MetodoPagamento` e `Currency`
  (nada fixo no código).

### Sem menções
- Nenhum arquivo versionado (fora de `.agent/` e do próprio teste de aceite) pode conter:
  `china`, `chinês`, `xangai`, `shanghai`, `kuai`, `yuan`, `rmb`, `cny`, `¥`, `alipay`,
  `wechat`, `weixin`, `zhifubao`, `viagem` (sem diferenciar maiúsculas). Isso inclui
  `tests/unit/` — atualize os testes unitários afetados.

## Subtarefas (uma por sessão)

1. Moedas e `PaymentMethod` v1 em `app/domain.py` (+ testes unitários afetados).
2. `MetodoPagamento`, `Pagamento.moeda` e `METODO_LABEL` (+ testes unitários).
3. Padrões de fuso/moeda nos módulos, `format_valor`/`Registro`, título do app.
4. Deploy (renomear Nginx, docs, Dockerfile, compose).
5. `evals/casos.yaml` + `verificar_cobertura` genérica.
6. Varredura final de menções (inclusive `tests/unit/`).

## Critérios de aceite

- `ACCEPTANCE_TASKS=T18 python -m pytest tests/acceptance/test_t18_generalizacao.py` passa 100%.
- `python -m pytest` (todas as tasks) e `python -m tools.run_evals --check` passam; `ruff` limpo.
- Somente os caminhos permitidos (+ `tests/unit/`).

## Fora de escopo

Categorias configuráveis pela planilha (sugestão futura); conversão de moedas.
