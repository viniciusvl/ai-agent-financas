---
id: T12
title: Roteador de intenção com Jev (escrita / leitura / outro)
branch: feature/T12-intent-router
depends_on: T01
acceptance: tests/acceptance/test_t12_router.py
allowed_paths:
  - app/router.py
---
## Contexto

Arquitetura v2 (#23, decisão D1). Toda mensagem passa primeiro pelo roteador. A decisão é feita
pelo **Jev** (TypeSafe): classificador hospedado que recebe um texto e perguntas fechadas e
devolve probabilidades. Se o Jev falhar (ou não houver chave), usa-se um classificador JSON no
DeepSeek. Instruções e opções são **constantes** em `app/prompts.py` (`ROUTER_INSTRUCTIONS`,
`ROUTER_CRITERIA`, `ROUTER_FALLBACK_SYSTEM_PROMPT`) — não as altere.
Referências: https://docs.typesafe.ai/api e o artigo na #23.

## Requisitos

### `IntentRouter.__init__`
Guarda os parâmetros (`self.threshold`, `self.model`, ...). Se `http` for `None`, cria
`httpx.AsyncClient(timeout=timeout)` próprio (fechado por `aclose`; client injetado não é fechado).

### `IntentRouter.route(texto) -> Rota`
1. `texto` vazio/só espaços → `Rota(OUTRO, confianca=0.0, origem="vazio")`, sem requisição.
2. Se `api_key` for vazia → vai direto para o fallback (passo 6).
3. `POST {base_url}/v1/systemone`, header `Authorization: Bearer <api_key>`, corpo **exato**:
   `{"model": <model>, "state": <texto>, "questions": {"intencao": {"type": "choice",
   "instructions": ROUTER_INSTRUCTIONS, "criteria": ROUTER_CRITERIA}}}`.
4. Status 429 ou 529 → **uma** nova tentativa após `await sleep(segundos)`, com `segundos` =
   header `retry-after` (número) limitado a 5, ou 1 se ausente/inválido. Falhou de novo → fallback.
5. Resposta 200: lê `answers["intencao"]`; `probabilities` é normalizado para somar 1 (se a soma
   for > 0); a intenção é `choice` (se for uma das três opções; senão a de maior probabilidade);
   `confianca` = probabilidade **normalizada** da intenção escolhida; `modelo` = campo `model` da
   resposta; `origem="jev"`.
6. **Fallback**: qualquer outra falha (status ≠ 2xx, timeout/erro de rede, JSON malformado,
   campos ausentes, nenhuma opção válida) → `await fallback.classify(texto)`. Sem fallback, ou se
   o fallback levantar exceção → `RouterError`.
7. Em qualquer origem (jev ou fallback): `confianca < threshold` → `intencao=OUTRO` (mantendo
   `confianca`, `probabilidades`, `origem` e `modelo`).
8. Nunca incluir a chave em logs ou mensagens de exceção. Logar intenção, confiança, origem e
   modelo em nível INFO.

### `DeepSeekIntentFallback`
- `__init__` igual ao padrão do `ExpenseExtractor` (client `openai.AsyncOpenAI` padrão ou injetado).
- `classify(texto)`: `client.chat.completions.create(model, temperature=0,
  response_format={"type": "json_object"}, messages=[system, user])`, com system =
  `ROUTER_FALLBACK_SYSTEM_PROMPT.format(**ROUTER_CRITERIA)` e user = `texto`.
- Resposta `{"intencao": "...", "confianca": x}` → `Rota(intencao, float(confianca) limitado a
  [0, 1], origem="fallback", modelo=<model>)`. Intenção inválida, JSON inválido, sem `choices`
  ou confiança ausente/não numérica → `Rota(OUTRO, 0.0, origem="fallback")`.
- Exceção da API → `RouterError`.

## Subtarefas (uma por sessão)

1. `Rota` em uso, `__init__`/`aclose`, chamada ao Jev e interpretação da resposta (passos 1, 3, 5).
2. Retry 429/529, fallback e `RouterError` (passos 2, 4, 6) + limiar (passo 7).
3. `DeepSeekIntentFallback`.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T12 python -m pytest tests/acceptance/test_t12_router.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente `app/router.py` (+ `tests/unit/`).

## Fora de escopo

Eval de acurácia e de viés de posição (T17); uso do roteador no bot (T16).
