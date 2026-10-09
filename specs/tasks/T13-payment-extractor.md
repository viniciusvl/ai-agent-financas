---
id: T13
title: Extrator de pagamento v2 (prompt de escrita estruturado)
branch: feature/T13-payment-extractor
depends_on: T10, T11
acceptance: tests/acceptance/test_t13_payment_extractor.py
allowed_paths:
  - app/payment_extractor.py
---
## Contexto

Arquitetura v2 (#23). Quando o roteador decide **escrita**, o `PaymentExtractor` transforma o
texto em `Pagamento` (T10). O prompt já existe em `app/prompts.py`
(`PAYMENT_EXTRACTION_SYSTEM_PROMPT`, placeholders `{agora}`, `{hoje}`, `{moeda_padrao}`,
`{schema}`) — não o altere. O mesmo padrão de robustez do extrator v1 (`app/extractor.py`, T04)
vale aqui; reaproveite o que fizer sentido importando de lá (sem alterar o arquivo).

## Requisitos

- `__init__`: guarda os atributos (`self.model`, `self.schema`, `self.default_currency`,
  `self.timezone`); client padrão `openai.AsyncOpenAI(api_key=..., base_url=...)` em `self.client`.
- `extract(texto, recebido_em)` (`recebido_em`: datetime com fuso):
  1. Texto vazio/só espaços → `ResultadoExtracao(erro=MSG_DEFAULT_NOT_EXPENSE)` sem chamar a API.
  2. `local = recebido_em.astimezone(ZoneInfo(timezone))`.
  3. Chamada: `client.chat.completions.create(model=self.model, temperature=0,
     response_format={"type": "json_object"}, messages=[system, user])`, system =
     `PAYMENT_EXTRACTION_SYSTEM_PROMPT.format(agora=local.strftime("%H:%M"),
     hoje=local.date().isoformat(), moeda_padrao=default_currency,
     schema=schema.prompt_context())`, user = `texto` exato.
  4. Exceção da API → `ExtractionError` (encadeada).
  5. Conteúdo ausente (sem `choices`/`message`), cercas de código, JSON inválido ou não-objeto
     → tratar como no v1; inválido → `ResultadoExtracao(erro=MSG_INVALID_RESPONSE)`.
  6. `is_pagamento` falso → `erro = motivo or MSG_DEFAULT_NOT_EXPENSE`.
  7. `valor_compra` ausente/`null` → `ResultadoExtracao(pergunta=MSG_PERGUNTA_VALOR)`.
  8. Método normalizado `credito_parcelado` (ou crédito com parcelas) e `quant_parcelas`
     ausente → `ResultadoExtracao(pergunta=MSG_PERGUNTA_PARCELAS)`. Use
     `app.payment` para normalizar o método antes de decidir.
  9. **Data/hora determinísticas:**
     - `data`: string ISO válida → essa data; senão `local.date()`.
     - `hora`: string `HH:MM` válida → essa hora; senão, se a data veio do LLM e é diferente
       de `local.date()` → `None` (hora desconhecida); senão → `local.time()` com
       segundos/microssegundos zerados.
  10. `descricao` ausente/vazia → `texto.strip()[:80]`.
  11. Moeda `null` → `default_currency`. Qualquer `valor_parcela` do JSON é ignorado.
  12. `Pagamento(..., texto_original=texto)`; `ValidationError` → `erro=MSG_INVALID_RESPONSE`.
- Logar a resposta bruta apenas em DEBUG.

## Subtarefas (uma por sessão)

1. `__init__`, montagem das mensagens e chamada à API (passos 1–4).
2. Parsing robusto e `is_pagamento` (passos 5–6).
3. Perguntas de dados faltantes, data/hora determinísticas e montagem do `Pagamento` (7–12).

## Critérios de aceite

- `ACCEPTANCE_TASKS=T13 python -m pytest tests/acceptance/test_t13_payment_extractor.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente `app/payment_extractor.py` (+ `tests/unit/`).

## Fora de escopo

Vários pagamentos numa mesma mensagem; conversa de múltiplos turnos (o bot só faz a pergunta).
