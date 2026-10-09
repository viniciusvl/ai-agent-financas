# AGENTS.md — protocolo dos agentes executores

Este repositório é desenvolvido em **agent loops spec-driven**:

- **Orquestrador/revisor (Claude):** escreve specs (`specs/`), testes de aceite
  (`tests/acceptance/`), cria as issues, dispara os loops, revisa os PRs e pede correções.
- **Executores (opencode + DeepSeek, agente `executor`):** implementam as tasks, uma
  subtarefa por sessão.
- **Runner** (`python -m tools.agent_loop.runner Txx`): abre uma sessão nova a cada volta,
  valida os critérios de aceite, garante o escopo e para quando tudo passa.

## Fontes de verdade

| O quê | Onde |
|---|---|
| Visão do produto | `specs/000-produto.md` |
| Spec da task (requisitos, subtarefas, aceite) | `specs/tasks/Txx-*.md` |
| Critérios de aceite executáveis | `tests/acceptance/test_txx_*.py` |
| Estado/handoff entre sessões | `.agent/state/Txx.md` |
| Feedback do runner e da revisão | anexo da sessão + comentários da issue |

## Protocolo de cada sessão

1. **Ler**: a spec da task, `.agent/state/Txx.md` (se existir) e o feedback anexado
   (resultado das validações da sessão anterior e revisão do orquestrador).
2. **Escolher**: se houver revisão com mudanças solicitadas ainda não resolvidas, ela tem
   prioridade. Senão, a **próxima subtarefa não concluída** da spec, na ordem.
3. **Implementar** só essa subtarefa, apenas nos caminhos permitidos (`allowed_paths` da spec)
   e, se quiser, testes extras em `tests/unit/`.
4. **Validar** (a variável `ACCEPTANCE_TASKS` já vem configurada pelo runner):
   - `python -m pytest <arquivo de aceite da task> -q`
   - `python -m pytest -q`
   - `python -m ruff format <arquivos alterados>` e `python -m ruff check .`
   Não é obrigatório que todos os testes de aceite passem ao fim de uma subtarefa
   intermediária, mas os testes ligados ao que você implementou devem passar.
5. **Atualizar** `.agent/state/Txx.md` exatamente neste formato:

   ```markdown
   # Txx — status

   ## Subtarefas
   - [x] 1. <nome da subtarefa 1>
   - [ ] 2. <nome da subtarefa 2>

   ## Revisões
   - [x] <item de revisão resolvido> (se houver)

   ## Última sessão (N)
   - O que foi feito: ...
   - Decisões tomadas: ...
   - Resultado dos testes: X passed, Y failed (aceite da task)

   ## Próximo passo
   <instrução objetiva para a próxima sessão>
   ```
6. **Commit e push** (Conventional Commits, em português):
   `git add -A` → `git commit -m "feat(Txx): <subtarefa>"` (ou `fix(Txx): ...` para correções
   de revisão) → `git push`.
7. **Comentar na issue**: `gh issue comment <número> --body-file .agent/state/Txx.md`.
8. **Encerrar** respondendo apenas `SESSION_DONE`.

## Proibido

- Alterar `tests/acceptance/`, `specs/`, `tools/`, `.opencode/`, `.github/`, `AGENTS.md`,
  `CLAUDE.md`, `app/messages.py`, `app/prompts.py`, `config/`, `pyproject.toml`,
  `requirements*.txt` — **exceto** caminhos listados explicitamente em `allowed_paths` da spec.
  (O runner reverte automaticamente qualquer alteração fora do escopo.)
- Pular/enfraquecer testes, usar `skip`/`xfail`, ou "hardcodar" respostas dos testes.
- Mudar de branch, fazer merge, rebase, `push --force` ou abrir PR (o runner faz).
- Gravar segredos em arquivos.

## Convenções de código

- Python 3.11+, type hints, `ruff` (linha ≤ 100), docstrings curtas em português.
- Sem dependências novas (se precisar, registre no status e pare — o orquestrador decide).
- Logs com `logging.getLogger(__name__)`; nunca logar tokens/chaves.
