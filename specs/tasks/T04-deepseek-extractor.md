---
id: T04
title: Extração do gasto com DeepSeek
branch: feature/T04-deepseek-extractor
depends_on: T01
acceptance: tests/acceptance/test_t04_extractor.py
allowed_paths:
  - app/extractor.py
---
## Contexto

`app/extractor.py` transforma texto livre em `Expense` usando a API do DeepSeek
(compatível com OpenAI, `chat.completions`). O prompt de sistema já existe em
`app/prompts.py` (`EXTRACTION_SYSTEM_PROMPT`, com placeholders `{today}` e
`{default_currency}`) — não altere o prompt.

## Requisitos

- `__init__(api_key, model="deepseek-flash", base_url="https://api.deepseek.com",
  default_currency="CNY", client=None)`: guarda atributos; client padrão
  `openai.AsyncOpenAI(api_key=..., base_url=...)` em `self.client`.
- `extract(text, today) -> ExtractionResult`:
  - texto vazio/só espaços → `ExtractionResult(error=MSG_DEFAULT_NOT_EXPENSE)` sem chamar a API;
  - chamada: `client.chat.completions.create(model=self.model, temperature=0,
    response_format={"type": "json_object"}, messages=[system, user])`; o system é o prompt
    formatado com `today.isoformat()` e a moeda padrão; o user é exatamente `text`;
  - exceção da API → `ExtractionError` (encadeada);
  - conteúdo: remover cercas de código (```json … ```) se houver; JSON inválido, vazio,
    `None` ou que não seja objeto → `ExtractionResult(error=MSG_INVALID_RESPONSE)`;
  - `is_expense` falso → `ExtractionResult(error=reason or MSG_DEFAULT_NOT_EXPENSE)`;
  - montar `Expense` com `amount`, `currency` (None → `default_currency`), `category`,
    `description`, `payment_method`, `spent_at` (data ISO válida, senão `today`),
    `raw_text=text`; `ValidationError` → `ExtractionResult(error=MSG_INVALID_RESPONSE)`.

## Subtarefas (uma por sessão)

1. `__init__` e chamada à API com os parâmetros corretos.
2. Parsing robusto do JSON (cercas, inválido, não-objeto) e `is_expense=false`.
3. Montagem do `Expense` (data, moeda padrão, erros de validação).

## Critérios de aceite

- `ACCEPTANCE_TASKS=T04 python -m pytest tests/acceptance/test_t04_extractor.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente `app/extractor.py` (+ `tests/unit/`).

## Fora de escopo

Múltiplos gastos numa mensagem, edição de campos por conversa.
