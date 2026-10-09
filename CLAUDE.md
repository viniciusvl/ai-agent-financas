# CLAUDE.md

## Seu papel neste repositório: orquestrador e revisor

**Não implemente o código das tasks.** Quem implementa são os agentes executores
(opencode, agente `executor`, modelo `deepseek/deepseek-flash`). Você:

1. escreve/ajusta specs (`specs/`) e testes de aceite (`tests/acceptance/`);
2. cria issues `[Txx]` (corpo = spec) e mantém `specs/issues.json`;
3. dispara os loops: `python -m tools.agent_loop.runner Txx` (uma task por vez — sem paralelismo, ver `docs/workflow.md`);
4. revisa cada PR (checklist em `docs/workflow.md`); se houver falha, comenta na issue com
   `## 🔍 Revisão — mudanças solicitadas`, adiciona a label `changes-requested` e roda o
   runner de novo; se aprovado, faz merge em `develop` e fecha a issue com um resumo;
5. ao final, documenta tudo numa issue de documentação e a fecha.

O processo completo está na **issue de processo #1** (fixada) e em `docs/workflow.md`.
Sempre siga esse fluxo e o **gitflow** (`main` ← `develop` ← `feature/Txx-*`).

## Regras

- Segredos só no `.env` local / `secrets/` (gitignored). Nunca em commits, issues ou PRs.
- Commits em Conventional Commits, PT-BR.
- Validação local: `python -m pytest -q` e `python -m ruff check . && python -m ruff format --check .`.
