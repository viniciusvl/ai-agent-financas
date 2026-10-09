# Fluxo de desenvolvimento — spec-driven + agent loops + gitflow

## Papéis

| Papel | Quem | Faz | Não faz |
|---|---|---|---|
| Orquestrador/revisor | Claude (Claude Code) | specs, testes de aceite, issues, dispara loops, revisa PRs, pede correções, faz merges e releases, documenta | não implementa código das tasks |
| Executor | agente `executor` do opencode com `deepseek/deepseek-flash` | implementa uma subtarefa por sessão, valida, commita, atualiza status | não muda specs/testes de aceite, não faz merge |
| Runner | `tools/agent_loop/runner.py` | abre sessões novas, reverte fora de escopo, valida aceite, comenta, abre PR | — |

## Gitflow

- `main`: só releases (merge de `release/x.y.z` ou `develop` com tag `vX.Y.Z`).
- `develop`: integração. Todo PR de task tem base `develop`.
- `feature/Txx-<slug>`: uma branch por task (definida no front matter da spec).
- `release/x.y.z` e `hotfix/x.y.z`: conforme gitflow clássico.
- Commits: Conventional Commits (`feat(T01): ...`, `fix(T01): ...`, `chore(...)`).

## Ciclo de uma task

```
spec + teste de aceite (Claude) ──► issue [Txx] (label task)
        │
        ▼
runner Txx ─► sessão 1 (opencode, contexto limpo) ─► commit + push + status + comentário
        │      ▲                                         │
        │      └──── validações falharam ◄── runner valida aceite/escopo/lint
        ▼
aceite ✅ ─► runner cria specs/done/Txx, abre PR → develop, label needs-review
        │
        ▼
revisão do Claude ─► problemas? comenta "## 🔍 Revisão — mudanças solicitadas",
        │             label changes-requested, roda o runner de novo (mesma branch)
        ▼
aprovado ─► merge (--merge) em develop, fecha a issue com resumo
```

### Handoff entre sessões (sem memória)

Cada sessão começa do zero e recebe, num arquivo anexado:
spec da task, caminho do status (`.agent/state/Txx.md`), resultado das validações da sessão
anterior e a revisão pendente (se houver). O agente termina toda sessão atualizando o status,
commitando e comentando na issue — esse é o "contexto" passado à próxima sessão.

### Critérios de aceite (verificados pelo runner)

1. `ACCEPTANCE_TASKS=Txx python -m pytest tests/acceptance/test_txx_*.py` 100% verde;
2. `python -m pytest` verde (sem regressão);
3. `ruff check .` e `ruff format --check .` limpos;
4. nenhum arquivo alterado fora de `allowed_paths` + `tests/unit/` + `.agent/state/Txx.md`.

### Checklist de revisão do orquestrador

- [ ] Diff só nos caminhos permitidos; testes de aceite intocados.
- [ ] Implementação segue a spec (não só os testes): erros, bordas, logs sem segredos.
- [ ] Sem "hardcode" para passar teste, sem `skip`/`xfail`, sem dependências novas.
- [ ] Código legível, tipado, coerente com o resto do projeto.
- [ ] CI verde no PR.

## Comandos

```bash
# rodar o loop de uma task (na raiz, árvore limpa)
python -m tools.agent_loop.runner T01

# tasks independentes em paralelo (cada uma no seu worktree)
python -m tools.agent_loop.runner T02 --worktree
python -m tools.agent_loop.runner T03 --worktree

# revisão
gh pr diff <n>; gh pr checks <n>
gh issue comment <issue> --body "## 🔍 Revisão — mudanças solicitadas ..."
gh issue edit <issue> --add-label changes-requested

# aprovação
gh pr merge <n> --merge --delete-branch
gh issue close <issue> --comment "..."
```

## Ordem das tasks

T01 → (T02, T03, T04, T05, T06 em paralelo) → T07 → T08 → T09 → release `v0.1.0`.
