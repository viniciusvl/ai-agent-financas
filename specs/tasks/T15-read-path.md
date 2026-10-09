---
id: T15
title: Caminho de leitura — consultas determinísticas + agente com tool calling
branch: feature/T15-read-path
depends_on: T10, T11
acceptance: tests/acceptance/test_t15_read_path.py
allowed_paths:
  - app/queries.py
  - app/read_agent.py
---
## Contexto

Arquitetura v2 (#23, consultas D6 provisórias). Para perguntas ("quanto gastei esta semana?"),
o **LLM só escolhe a consulta e os argumentos** (tool calling); a aplicação lê a planilha,
calcula com `Decimal` e formata a resposta com templates. O LLM nunca produz números.
Prompt: `READ_AGENT_SYSTEM_PROMPT` em `app/prompts.py` (placeholders `{hoje}`, `{dia_semana}`);
textos: `app/messages.py` (`MSG_LEITURA_NAO_SUPORTADA`, `MSG_NENHUM_GASTO`,
`MSG_NENHUMA_PARCELA`). Não altere esses arquivos.

## Requisitos — `app/queries.py` (puro)

- `format_valor(moeda, valor)`: 2 casas, milhar com `.` e decimal com `,`; prefixos
  `CNY`→`¥ `, `BRL`→`R$ `, `USD`→`US$ `, outras → `"<MOEDA> "`. Ex.: `¥ 1.234,56`, `R$ 0,50`.
- `format_totais(totais)`: moedas em ordem alfabética, `format_valor` unidos por `" + "`;
  vazio → `MSG_NENHUM_GASTO`.
- `parse_rows(schema, rows)`: `rows` são as linhas **sem** o cabeçalho. Para cada linha, pega as
  colunas pelo `campo` do schema:
  - `data` (obrigatória): `date`/`datetime` aceitos direto; string tentada com o `formato` da
    coluna, depois `%Y-%m-%d`, depois `%d/%m/%Y`.
  - `valor_compra` (obrigatório): número ou string (aceita `1.234,56`, `1234.56`, `R$ 10,00`,
    `¥ 35`); > 0.
  - `moeda` (padrão `CNY`), `categoria` (`outros`), `metodo_pagamento` (`outro`),
    `quant_parcelas` (1; inteiro, aceita `"3"`/`3.0`), `descricao` (`""`).
  - Linha vazia, data ou valor inválidos → **ignorada** (log WARNING com o número da linha).
  - Colunas ausentes no schema → valores padrão.
- Todas as consultas usam período **inclusivo** e somam por moeda:
  - `total_periodo(regs, inicio, fim) -> {moeda: total}`.
  - `total_por_categoria` / `total_por_metodo` → `{categoria|metodo: {moeda: total}}`.
  - `ultimos(regs, n)` → os `n` mais recentes por data (desc); empate mantém a ordem inversa
    da planilha (o gravado depois aparece primeiro).
  - `parcelas_futuras(regs, referencia)` → `{"AAAA-MM": {moeda: total}}`. Para cada registro
    `credito_parcelado` com `quant_parcelas >= 2`: as parcelas vêm de
    `app.payment.calcular_parcelas`; a parcela *k* (1..n) vence no mês da compra + *k*. Entram
    as parcelas com vencimento **no mês de `referencia` ou depois**.
- `GastosRepository(worksheet, schema, ttl_seconds=60, clock)`: `registros()` chama
  `worksheet.get_all_values(value_render_option="UNFORMATTED_VALUE",
  date_time_render_option="FORMATTED_STRING")`, descarta a 1ª linha (cabeçalho) e aplica
  `parse_rows`; resultado em cache por `ttl_seconds` (pelo `clock`); `invalidate()` limpa o cache.
  Erros do worksheet → `ReadError` (definido em `app/queries.py`, reexportado por
  `app/read_agent.py`).

## Requisitos — `app/read_agent.py`

- `TOOLS`: 5 ferramentas no formato OpenAI (`{"type": "function", "function": {name,
  description, parameters}}`): `total_periodo(inicio, fim)`, `total_por_categoria(inicio, fim)`,
  `total_por_metodo(inicio, fim)` (datas `YYYY-MM-DD`, obrigatórias), `ultimos_gastos(n)`
  (inteiro, opcional) e `parcelas_futuras()` (sem parâmetros).
- `answer(pergunta, agora)`:
  1. `hoje = agora.astimezone(ZoneInfo(timezone)).date()`; `dia_semana` em português
     (`segunda-feira` … `domingo`).
  2. `client.chat.completions.create(model, temperature=0, tools=TOOLS, tool_choice="auto",
     messages=[system (prompt formatado), user (pergunta)])`. Exceção → `ReadError`.
  3. Sem `tool_calls` (ou resposta malformada), ferramenta desconhecida, JSON de argumentos
     inválido, argumento obrigatório ausente ou data inválida → `MSG_LEITURA_NAO_SUPORTADA`.
  4. Executa a consulta sobre `repo.registros()` (exceções → `ReadError`). `inicio > fim` →
     troca; `n` ausente → 5, limitado a 1..20; `parcelas_futuras` usa `referencia=hoje`.
  5. Formata (datas `dd/mm/aaaa`; `T` = `format_totais`):
     - `total_periodo` → `💰 Total de {inicio} a {fim}: {T}`
     - `total_por_categoria` → `📊 Gastos por categoria de {inicio} a {fim}:` + uma linha
       `• {categoria}: {T}` por categoria (ordem alfabética); sem dados → linha
       `MSG_NENHUM_GASTO`.
     - `total_por_metodo` → `💳 Gastos por forma de pagamento de {inicio} a {fim}:` + linhas
       `• {metodo}: {T}` (mesmas regras).
     - `ultimos_gastos` → `🧾 Últimos gastos:` + linhas
       `• {dd/mm} — {descricao} — {format_valor}`; sem dados → `MSG_NENHUM_GASTO`.
     - `parcelas_futuras` → `📅 Parcelas futuras:` + linhas `• {MM/AAAA}: {T}` (ordem
       cronológica); sem dados → `MSG_NENHUMA_PARCELA`.
     Linhas separadas por `\n`.

## Subtarefas (uma por sessão)

1. `format_valor`, `format_totais`, `parse_rows`.
2. Consultas (`total_*`, `ultimos`, `parcelas_futuras`) e `GastosRepository`.
3. `TOOLS` e chamada ao LLM em `ReadAgent.answer` (passos 1–3).
4. Execução e formatação das respostas (passos 4–5).

## Critérios de aceite

- `ACCEPTANCE_TASKS=T15 python -m pytest tests/acceptance/test_t15_read_path.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente os caminhos permitidos (+ `tests/unit/`).

## Fora de escopo

Gráficos; filtro por usuário; conversão de moedas.
