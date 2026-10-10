---
id: T17
title: Conjunto de avaliação (evals) do roteador e do extrator
branch: feature/T17-evals
depends_on: T12, T13
acceptance: tests/acceptance/test_t17_evals.py
allowed_paths:
  - evals/casos.yaml
  - tools/run_evals.py
---
## Contexto

Arquitetura v2 (#23). Sem medição não dá para saber se uma mudança de prompt melhorou ou piorou.
Esta task cria o conjunto de casos e o avaliador. **Exceção ao AGENTS.md:** nesta task você
pode editar `tools/run_evals.py` (stub já existe). A execução `--live` (com rede) é feita
pelo orquestrador; você valida com `--check` e com os testes.

## Requisitos

### `evals/casos.yaml`
```yaml
casos:
  - id: e001
    texto: "paguei 80 reais no mercado com pix"
    rota: escrita            # escrita | leitura | outro
    esperado:                # só para rota escrita; apenas os campos que se quer conferir
      valor_compra: 80
      moeda: BRL
      metodo_pagamento: pix
      categoria: transporte
```
- **≥ 60 casos**, `id` únicos, textos realistas em PT-BR de gastos pessoais (gírias, erros
  típicos de transcrição de áudio: sem pontuação, números por extenso como "oitenta reais").
- Cobertura mínima (validada por `verificar_cobertura`):
  - ≥ 30 `escrita`, ≥ 15 `leitura`, ≥ 10 `outro`;
  - entre os de escrita com `metodo_pagamento` esperado: cada um dos 8 métodos ≥ 2 vezes;
  - moedas esperadas: cada `Currency` ≥ 3 e a mais frequente ≥ 10;
  - ≥ 6 casos `credito_parcelado` com `quant_parcelas` esperado, com ≥ 4 valores distintos;
  - todo caso `escrita` tem `esperado.valor_compra`.

### `tools/run_evals.py`
- `load_casos(path)`: lê o YAML (`yaml.safe_load`); valida `id` único, `texto` não vazio,
  `rota` ∈ {escrita, leitura, outro}, `esperado` só com chaves de `CAMPOS_AVALIADOS` e só em
  casos de escrita → senão `CasosError` com o `id` do caso.
- `verificar_cobertura(casos)`: aplica a cobertura mínima acima → `CasosError` descrevendo o
  que falta.
- `avaliar(casos, router, extractor, recebido_em)` (assíncrono):
  - para cada caso: `rota = await router.route(texto)`; acerto se `rota.intencao.value == caso.rota`;
  - para casos de escrita: `res = await extractor.extract(texto, recebido_em)`; cada campo de
    `esperado` é comparado com `res.pagamento` (`Decimal(str(esperado))` para `valor_compra`;
    `.value` para enums; ausência de pagamento = todos os campos errados);
  - exceções de um caso contam como erro daquele caso (não interrompem a avaliação);
  - latência: tempo de `route` + `extract` por caso (`time.perf_counter`), média em ms;
  - `falhas`: lista de strings `"<id>: <motivo>"`.
  - `acuracia_campos` = acertos / total de campos avaliados; `acertos_por_campo` por campo.
- `render_relatorio(rel, quando)` → Markdown com título `# Evals — <AAAA-MM-DD HH:MM>`, as
  métricas em porcentagem com 1 casa (`95.0%`), limiares, latência e a lista de falhas.
- `main(argv)` (argparse):
  - `--check`: `load_casos` + `verificar_cobertura`; imprime `OK: <n> casos` e retorna 0, ou
    a mensagem do erro e retorna 1. Sem rede.
  - `--live`: monta `IntentRouter` (+ `DeepSeekIntentFallback`) e `PaymentExtractor` com
    `get_settings()` e `SheetSchema.load(settings.sheet_schema_path)`; roda `avaliar`; grava
    `evals/resultados/<AAAA-MM-DD>.md`; retorna 0 se `acuracia_rota >= LIMIAR_ROTA` e
    `acuracia_campos >= LIMIAR_CAMPOS`, senão 1.
  - sem argumentos → equivalente a `--check`.

## Subtarefas (uma por sessão)

1. `evals/casos.yaml` com os primeiros ~30 casos + `load_casos`.
2. Completar os casos até a cobertura + `verificar_cobertura` + `--check`.
3. `avaliar`, `render_relatorio` e `--live`.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T17 python -m pytest tests/acceptance/test_t17_evals.py` passa 100%.
- `python -m tools.run_evals --check` retorna 0.
- `python -m pytest` passa e `ruff` limpo. Somente os caminhos permitidos (+ `tests/unit/`).

## Fora de escopo

Fine-tuning; avaliação do agente de leitura (T15).
