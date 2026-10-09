"""Runner dos agent loops: executa sessões do agente `executor` (opencode + DeepSeek) até que
os critérios de aceite da task sejam atingidos.

Uso:
    python -m tools.agent_loop.runner T01 [--max-sessions 8] [--force]

As tasks rodam UMA DE CADA VEZ, no checkout principal. Não há isolamento paralelo confiável:
o opencode identifica o projeto pelo repositório (remoto/commit raiz) e executa as ferramentas
no diretório registrado do projeto — git worktrees não registrados e clones com o mesmo
`origin` acabam editando/commitando no checkout principal (incidente dos PRs #15/#16).

Cada volta do loop:
  1. abre uma sessão NOVA do opencode (sem memória) com a spec, o status e o feedback;
  2. o agente executa uma subtarefa, atualiza `.agent/state/Txx.md`, commita, faz push e comenta;
  3. o runner reverte alterações fora do escopo, commita sobras e faz push;
  4. o runner valida os critérios de aceite e comenta o resultado na issue;
  5. se tudo passou: cria o marcador specs/done/Txx, abre o PR para develop e para.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_BRANCH = "develop"
REVIEW_MARKER = "## 🔍 Revisão"
SCOPE_ALWAYS_ALLOWED = ("tests/unit/",)
SESSION_TIMEOUT_S = 20 * 60  # sessões normais levam 1–4 min
IDLE_TIMEOUT_S = 6 * 60  # sem nenhum evento do opencode: chamada ao modelo travada
TAIL_CHARS = 3500


# --------------------------------------------------------------------------- spec


@dataclass
class TaskSpec:
    id: str
    title: str
    branch: str
    acceptance: str
    path: Path
    body: str
    depends_on: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)

    @property
    def state_file(self) -> str:
        return f".agent/state/{self.id}.md"


def parse_front_matter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---"):
        raise ValueError("spec sem front matter")
    _, header, body = text.split("---", 2)
    data: dict[str, object] = {}
    current_list: str | None = None
    for raw in header.strip().splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("- ") and current_list:
            data[current_list].append(line.strip()[2:].strip())  # type: ignore[union-attr]
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value:
            data[key] = value
            current_list = None
        else:
            data[key] = []
            current_list = key
    return data, body.strip()


def load_spec(task_id: str, root: Path = ROOT) -> TaskSpec:
    matches = sorted((root / "specs" / "tasks").glob(f"{task_id}-*.md"))
    if not matches:
        raise SystemExit(f"spec não encontrada para {task_id}")
    path = matches[0]
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    deps = meta.get("depends_on") or []
    if isinstance(deps, str):
        deps = [d.strip() for d in deps.split(",") if d.strip()]
    return TaskSpec(
        id=str(meta["id"]),
        title=str(meta["title"]),
        branch=str(meta["branch"]),
        acceptance=str(meta["acceptance"]),
        path=path,
        body=body,
        depends_on=list(deps),
        allowed_paths=list(meta.get("allowed_paths") or []),  # type: ignore[arg-type]
    )


def issue_number(task_id: str, root: Path = ROOT) -> int:
    mapping = json.loads((root / "specs" / "issues.json").read_text(encoding="utf-8"))
    return int(mapping[task_id])


# --------------------------------------------------------------------------- shell


def run(
    args: list[str],
    cwd: Path,
    check: bool = True,
    env: dict[str, str] | None = None,
    timeout: int | None = 600,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"comando falhou: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result


def git(cwd: Path, *args: str, check: bool = True) -> str:
    return run(["git", *args], cwd, check=check).stdout.strip()


def gh(cwd: Path, *args: str, check: bool = True) -> str:
    return run(["gh", *args], cwd, check=check).stdout.strip()


def log(msg: str) -> None:
    print(f"[runner {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def opencode_bin() -> str:
    override = os.environ.get("OPENCODE_BIN")
    if override:
        return override
    found = shutil.which("opencode")
    if not found:
        raise SystemExit("opencode não encontrado no PATH (defina OPENCODE_BIN)")
    if os.name == "nt":
        # O shim .cmd do npm quebra argumentos; usar o executável nativo diretamente.
        native = Path(found).parent / "node_modules" / "@opencode" / "cli" / "bin" / "opencode.exe"
        if native.exists():
            return str(native)
    return found


def task_env(task: TaskSpec) -> dict[str, str]:
    """Ambiente das sessões/validações: o Python do runner vem primeiro no PATH.

    No Windows, o atalho da Microsoft Store (WindowsApps\python.exe) pode ficar à frente do
    interpretador real e quebrar `python -m pytest` dentro das sessões do agente.
    """
    path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
    return {**os.environ, "PATH": path, "ACCEPTANCE_TASKS": task.id, "PYTHONIOENCODING": "utf-8"}


def tail(text: str, limit: int = TAIL_CHARS) -> str:
    text = text.strip()
    return text if len(text) <= limit else "…\n" + text[-limit:]


# --------------------------------------------------------------------------- workspace


def prepare_workspace(task: TaskSpec) -> Path:
    cwd = ROOT
    git(cwd, "fetch", "origin", "--prune")
    remote_exists = bool(git(cwd, "ls-remote", "--heads", "origin", task.branch))
    local_exists = bool(git(cwd, "branch", "--list", task.branch))

    if git(cwd, "status", "--porcelain"):
        raise SystemExit(f"{cwd} com alterações não commitadas; resolva antes de rodar o loop")
    if local_exists:
        git(cwd, "checkout", task.branch)
    elif remote_exists:
        git(cwd, "checkout", "-b", task.branch, f"origin/{task.branch}")
    else:
        git(cwd, "checkout", "-b", task.branch, f"origin/{BASE_BRANCH}")
    install_pre_push_hook(cwd)

    if remote_exists:
        git(cwd, "pull", "--ff-only", "origin", task.branch, check=False)
    sync_with_base(task, cwd)
    git(cwd, "push", "-u", "origin", task.branch)
    return cwd


def sync_with_base(task: TaskSpec, cwd: Path) -> None:
    """Traz a develop atual para a branch da task (correções de infra, tasks já mergeadas)."""
    merged = run(["git", "merge", "--no-edit", f"origin/{BASE_BRANCH}"], cwd, check=False)
    if merged.returncode != 0:
        git(cwd, "merge", "--abort", check=False)
        raise SystemExit(
            f"conflito ao integrar {BASE_BRANCH} em {task.branch}; o orquestrador deve resolver"
        )


def done_tasks_on_base(cwd: Path) -> set[str]:
    listing = git(
        cwd, "ls-tree", "--name-only", f"origin/{BASE_BRANCH}", "specs/done/", check=False
    )
    return {Path(line).name for line in listing.splitlines() if Path(line).name.startswith("T")}


def done_marker(task: TaskSpec) -> str:
    return f"specs/done/{task.id}"


def in_scope(task: TaskSpec, path: str) -> bool:
    allowed = [*task.allowed_paths, *SCOPE_ALWAYS_ALLOWED, task.state_file, done_marker(task)]
    for entry in allowed:
        if entry.endswith("/") and path.startswith(entry):
            return True
        if path == entry:
            return True
    return False


def changed_files(cwd: Path) -> list[str]:
    committed = git(cwd, "diff", "--name-only", f"origin/{BASE_BRANCH}...HEAD").splitlines()
    pending = [line[3:].strip() for line in git(cwd, "status", "--porcelain").splitlines()]
    return sorted({p.strip('"') for p in [*committed, *pending] if p})


def enforce_scope(task: TaskSpec, cwd: Path) -> list[str]:
    """Reverte para o estado de develop qualquer arquivo alterado fora do escopo da task."""
    reverted = []
    for path in changed_files(cwd):
        if in_scope(task, path):
            continue
        exists_on_base = (
            run(
                ["git", "cat-file", "-e", f"origin/{BASE_BRANCH}:{path}"], cwd, check=False
            ).returncode
            == 0
        )
        if exists_on_base:
            git(cwd, "checkout", f"origin/{BASE_BRANCH}", "--", path)
        else:
            git(cwd, "rm", "-rf", "--cached", "--ignore-unmatch", "--", path)
            target = cwd / path
            if target.is_file():
                target.unlink()
        reverted.append(path)
    return reverted


def commit_leftovers(cwd: Path, message: str) -> bool:
    if not git(cwd, "status", "--porcelain"):
        return False
    git(cwd, "add", "-A")
    git(cwd, "commit", "-m", message)
    return True


# --------------------------------------------------------------------------- checks


@dataclass
class CheckResult:
    passed: bool
    report: str
    acceptance_summary: str


def run_checks(task: TaskSpec, cwd: Path) -> CheckResult:
    env = task_env(task)
    py = sys.executable
    checks = [
        ("Aceite da task", [py, "-m", "pytest", task.acceptance, "-q", "-rfE", "--no-header"]),
        ("Suíte completa", [py, "-m", "pytest", "-q", "--no-header"]),
        ("Lint (ruff check)", [py, "-m", "ruff", "check", "."]),
        ("Formatação (ruff format --check)", [py, "-m", "ruff", "format", "--check", "."]),
    ]
    lines, all_ok, acceptance_summary = [], True, ""
    for name, cmd in checks:
        result = run(cmd, cwd, check=False, env=env, timeout=900)
        ok = result.returncode == 0
        all_ok &= ok
        output = (result.stdout + "\n" + result.stderr).strip()
        if name == "Aceite da task":
            acceptance_summary = output.splitlines()[-1] if output else ""
        lines.append(f"### {'✅' if ok else '❌'} {name}")
        if not ok:
            lines.append(f"```\n{tail(output)}\n```")
    out_of_scope = [p for p in changed_files(cwd) if not in_scope(task, p)]
    if out_of_scope:
        all_ok = False
        lines.append("### ❌ Escopo")
        lines.append("Arquivos fora do escopo: " + ", ".join(f"`{p}`" for p in out_of_scope))
    else:
        lines.append("### ✅ Escopo")
    return CheckResult(all_ok, "\n".join(lines), acceptance_summary)


def review_addressed(task: TaskSpec, cwd: Path, desde: str) -> bool:
    """True se há ao menos um commit `fix(<id>)` desde `desde` (revisão atendida)."""
    return bool(git(cwd, "log", "--oneline", "--grep", f"fix({task.id})", f"{desde}..HEAD"))


# --------------------------------------------------------------------------- github


def issue_comments(cwd: Path, number: int) -> list[dict]:
    raw = gh(cwd, "issue", "view", str(number), "--json", "comments", check=False)
    return json.loads(raw).get("comments", []) if raw else []


def pending_review(cwd: Path, number: int) -> str:
    """Último comentário de revisão do orquestrador (se a issue estiver com changes-requested)."""
    labels = gh(cwd, "issue", "view", str(number), "--json", "labels", "-q", ".labels[].name")
    if "changes-requested" not in labels.split():
        return ""
    reviews = [
        c["body"] for c in issue_comments(cwd, number) if c["body"].startswith(REVIEW_MARKER)
    ]
    return reviews[-1] if reviews else ""


def set_labels(cwd: Path, number: int, add: list[str], remove: list[str]) -> None:
    args = ["issue", "edit", str(number)]
    for label in add:
        args += ["--add-label", label]
    for label in remove:
        args += ["--remove-label", label]
    gh(cwd, *args, check=False)


def comment(cwd: Path, number: int, body: str) -> None:
    body_file = cwd / ".agent" / "logs" / "comment.md"
    body_file.parent.mkdir(parents=True, exist_ok=True)
    body_file.write_text(body, encoding="utf-8", newline="\n")
    gh(cwd, "issue", "comment", str(number), "--body-file", str(body_file), check=False)


def ensure_pr(task: TaskSpec, number: int, cwd: Path) -> str:
    existing = gh(
        cwd,
        "pr",
        "list",
        "--head",
        task.branch,
        "--state",
        "open",
        "--json",
        "url",
        "-q",
        ".[0].url",
    )
    if existing:
        return existing
    body = (
        f"Implementa **{task.id} — {task.title}** (issue #{number}).\n\n"
        f"- Spec: `{task.path.relative_to(ROOT).as_posix()}`\n"
        f"- Aceite: `{task.acceptance}`\n"
        f"- Status/handoff: `{task.state_file}`\n\n"
        "Gerado pelo agent loop (opencode + DeepSeek). Aguardando revisão do orquestrador.\n\n"
        f"Refs #{number}\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"
    )
    return gh(
        cwd,
        "pr",
        "create",
        "--base",
        BASE_BRANCH,
        "--head",
        task.branch,
        "--title",
        f"feat({task.id}): {task.title}",
        "--body",
        body,
    )


# --------------------------------------------------------------------------- sessão


def build_prompt(task: TaskSpec, number: int, session: int, last_report: str, review: str) -> str:
    parts = [
        f"# Sessão {session} — task {task.id}: {task.title}",
        f"- Issue: #{number} (comente com `gh issue comment {number} --body-file "
        f"{task.state_file}`)",
        f"- Branch atual: `{task.branch}` (não troque de branch)",
        f"- Spec: `{task.path.relative_to(ROOT).as_posix()}` — leia inteira antes de começar",
        f"- Teste de aceite: `python -m pytest {task.acceptance} -q`",
        f"- Arquivo de status: `{task.state_file}`",
        "- Caminhos permitidos: "
        + ", ".join(f"`{p}`" for p in task.allowed_paths)
        + ", `tests/unit/`",
        "",
        "Siga o protocolo de `AGENTS.md`: UMA subtarefa (ou as correções da revisão), validar, "
        "atualizar o status, commit, push, comentar na issue e responder `SESSION_DONE`.",
    ]
    if review:
        parts += ["", "## ⚠️ Revisão do orquestrador — PRIORIDADE MÁXIMA", review]
    if last_report:
        parts += ["", "## Resultado das validações do runner após a sessão anterior", last_report]
    else:
        parts += ["", "## Resultado das validações", "Nenhuma validação anterior nesta execução."]
    return "\n".join(parts)


def run_with_watchdog(
    cmd: list[str], cwd: Path, env: dict[str, str], total_timeout: float, idle_timeout: float
) -> tuple[str, int]:
    """Executa o comando lendo a saída em streaming e o encerra se ficar ocioso.

    Com `--format json` o opencode emite eventos durante a sessão; uma chamada ao modelo
    travada fica em silêncio. Sem saída por `idle_timeout` s (ou acima de `total_timeout` s),
    o processo é encerrado e o código de saída é -1.
    """
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        # `opencode run` lê a mensagem também do stdin: herdado e aberto, ele espera um EOF
        # que nunca chega e a sessão trava sem emitir nenhum evento.
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    lines: list[str] = []
    last_activity = [time.monotonic()]

    def reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            last_activity[0] = time.monotonic()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    start = time.monotonic()
    killed_reason = ""
    while proc.poll() is None:
        now = time.monotonic()
        if now - last_activity[0] > idle_timeout:
            killed_reason = f"sem atividade por {idle_timeout:.0f}s"
        elif now - start > total_timeout:
            killed_reason = f"acima de {total_timeout:.0f}s"
        if killed_reason:
            proc.kill()
            break
        time.sleep(1)
    proc.wait()
    thread.join(timeout=5)
    if killed_reason:
        log(f"sessão encerrada pelo watchdog ({killed_reason})")
        return "".join(lines), -1
    return "".join(lines), proc.returncode


def run_session(task: TaskSpec, cwd: Path, session: int, prompt: str) -> str:
    log_dir = cwd / ".agent" / "logs" / task.id
    log_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = log_dir / f"session-{session}-prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8", newline="\n")
    log_file = log_dir / f"session-{session}.jsonl"
    env = task_env(task)
    cmd = [
        opencode_bin(),
        "run",
        # Servidor privado, sem depender do serviço em segundo plano compartilhado.
        "--standalone",
        "--agent",
        "executor",
        "--auto",
        "--format",
        "json",
        "--title",
        f"{task.id} sessão {session}",
        "--file",
        str(prompt_file),
        f"Execute a sessão {session} da task {task.id} seguindo as instruções do arquivo anexado.",
    ]
    output, code = run_with_watchdog(cmd, cwd, env, SESSION_TIMEOUT_S, IDLE_TIMEOUT_S)
    log_file.write_text(output or "", encoding="utf-8")
    texts = []
    for line in (output or "").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "text":
            texts.append(event.get("part", {}).get("text", ""))
    final = texts[-1].strip() if texts else ""
    log(f"sessão {session} finalizada (exit={code}): {final[:120]!r}")
    return final


# --------------------------------------------------------------------------- main


PRE_PUSH_HOOK = """#!/bin/sh
# Instalado pelo runner do agent loop: main/develop só mudam via PR.
while read local_ref local_sha remote_ref remote_sha; do
  case "$remote_ref" in
    refs/heads/main|refs/heads/develop)
      echo "pre-push: push direto para ${remote_ref#refs/heads/} bloqueado (use PR)" >&2
      exit 1;;
  esac
done
exit 0
"""


def install_pre_push_hook(repo: Path = ROOT) -> None:
    hooks = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "pre-push").write_text(PRE_PUSH_HOOK, encoding="utf-8", newline="\n")


def protected_state(cwd: Path) -> tuple[str, ...]:
    """Fotografia das refs locais main/develop e da branch atual do checkout.

    O remoto é protegido pelo pre-push hook; aqui não se olha origin/* porque o orquestrador
    pode fazer merge de PRs enquanto um loop roda.
    """
    refs = ["main", BASE_BRANCH]
    shas = tuple(git(cwd, "rev-parse", "--verify", "-q", ref, check=False) for ref in refs)
    return (*shas, git(cwd, "branch", "--show-current"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent loop de uma task spec-driven")
    parser.add_argument("task", help="ID da task, ex.: T01")
    parser.add_argument("--max-sessions", type=int, default=8)
    parser.add_argument("--force", action="store_true", help="ignorar dependências pendentes")
    args = parser.parse_args(argv)

    task = load_spec(args.task)
    number = issue_number(task.id)
    install_pre_push_hook()
    cwd = prepare_workspace(task)
    log(f"{task.id} em {cwd} (branch {task.branch}, issue #{number})")

    missing = [d for d in task.depends_on if d not in done_tasks_on_base(cwd)]
    if missing and not args.force:
        log(f"dependências ainda não mergeadas em {BASE_BRANCH}: {missing}")
        return 3

    set_labels(cwd, number, add=["in-progress"], remove=["blocked", "needs-review"])
    review = pending_review(cwd, number)
    last_report = ""
    head_inicio = git(cwd, "rev-parse", "HEAD")

    for session in range(1, args.max_sessions + 1):
        log(f"iniciando sessão {session}/{args.max_sessions}")
        head_before = git(cwd, "rev-parse", "HEAD")
        guard_before = protected_state(cwd)
        final = run_session(
            task, cwd, session, build_prompt(task, number, session, last_report, review)
        )
        if protected_state(cwd) != guard_before:
            set_labels(cwd, number, add=["blocked"], remove=["in-progress"])
            comment(
                cwd,
                number,
                f"⛔ Sessão {session} alterou `{BASE_BRANCH}`/`main` ou o checkout principal. "
                "Loop interrompido; o orquestrador precisa investigar.",
            )
            log("ALERTA: branches protegidas ou checkout principal alterados — abortando")
            return 4

        reverted = enforce_scope(task, cwd)
        if reverted:
            commit_leftovers(cwd, f"chore({task.id}): runner reverteu alterações fora do escopo")
        commit_leftovers(cwd, f"chore({task.id}): alterações não commitadas da sessão {session}")
        git(cwd, "push", "origin", task.branch, check=False)
        commits = git(cwd, "log", "--oneline", f"{head_before}..HEAD")

        result = run_checks(task, cwd)
        if result.passed and review and not review_addressed(task, cwd, head_inicio):
            # Os testes de aceite não cobrem os itens da revisão: sem um commit fix(Txx)
            # nesta execução, a revisão não foi atendida (ex.: sessão travada sem mudanças).
            result = CheckResult(
                False,
                result.report
                + f"\n### ❌ Revisão pendente\nNenhum commit `fix({task.id}): ...` nesta execução"
                " — atenda aos itens da revisão do orquestrador.",
                result.acceptance_summary,
            )
        status = "✅ critérios de aceite atingidos" if result.passed else "❌ ainda não aceito"
        body = [
            f"## 🤖 Runner — {task.id} sessão {session}: {status}",
            f"Aceite: `{result.acceptance_summary}`",
            "",
            "**Commits da sessão:**",
            f"```\n{commits or '(nenhum commit)'}\n```",
        ]
        if reverted:
            body.append("**⚠️ Revertidos (fora do escopo):** " + ", ".join(reverted))
        if final:
            body.append(f"**Resposta final do agente:** {tail(final, 300)}")
        body += ["", result.report]
        comment(cwd, number, "\n".join(body))

        if result.passed:
            marker = cwd / done_marker(task)
            if not marker.exists():
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_bytes(b"")
                commit_leftovers(cwd, f"chore({task.id}): marca task como concluída")
                git(cwd, "push", "origin", task.branch)
            pr_url = ensure_pr(task, number, cwd)
            set_labels(
                cwd, number, add=["needs-review"], remove=["in-progress", "changes-requested"]
            )
            comment(cwd, number, f"✅ Aceite atingido. PR para revisão: {pr_url}")
            log(f"{task.id} aceita — PR: {pr_url}")
            return 0

        last_report = result.report

    set_labels(cwd, number, add=["blocked"], remove=["in-progress"])
    comment(cwd, number, f"⛔ {task.id} não atingiu o aceite em {args.max_sessions} sessões.")
    log(f"{task.id} bloqueada após {args.max_sessions} sessões")
    return 2


if __name__ == "__main__":
    sys.exit(main())
