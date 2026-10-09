"""Runner dos agent loops: executa sessões do agente `executor` (opencode + DeepSeek) até que
os critérios de aceite da task sejam atingidos.

Uso:
    python -m tools.agent_loop.runner T01 [--max-sessions 8] [--worktree] [--force]

Cada volta do loop:
  1. abre uma sessão NOVA do opencode (sem memória) com a spec, o status e o feedback;
  2. o agente executa uma subtarefa, atualiza `.agent/state/Txx.md`, commita, faz push e comenta;
  3. o runner reverte alterações fora do escopo, commita sobras e faz push;
  4. o runner valida os critérios de aceite e comenta o resultado na issue;
  5. se tudo passou: marca a task em specs/tasks_done.txt, abre o PR para develop e para.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_BRANCH = "develop"
REVIEW_MARKER = "## 🔍 Revisão"
SCOPE_ALWAYS_ALLOWED = ("tests/unit/", "specs/tasks_done.txt")
SESSION_TIMEOUT_S = 40 * 60
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


def tail(text: str, limit: int = TAIL_CHARS) -> str:
    text = text.strip()
    return text if len(text) <= limit else "…\n" + text[-limit:]


# --------------------------------------------------------------------------- workspace


def prepare_workspace(task: TaskSpec, use_worktree: bool) -> Path:
    git(ROOT, "fetch", "origin", "--prune")
    remote_exists = bool(git(ROOT, "ls-remote", "--heads", "origin", task.branch))
    local_exists = bool(git(ROOT, "branch", "--list", task.branch))

    if use_worktree:
        cwd = ROOT.parent / f"{ROOT.name}-wt" / task.id
        if not cwd.exists():
            cwd.parent.mkdir(parents=True, exist_ok=True)
            if local_exists:
                git(ROOT, "worktree", "add", str(cwd), task.branch)
            elif remote_exists:
                git(ROOT, "worktree", "add", "-b", task.branch, str(cwd), f"origin/{task.branch}")
            else:
                git(ROOT, "worktree", "add", "-b", task.branch, str(cwd), f"origin/{BASE_BRANCH}")
    else:
        cwd = ROOT
        if git(cwd, "status", "--porcelain"):
            raise SystemExit("working tree com alterações; faça commit/stash ou use --worktree")
        if local_exists:
            git(cwd, "checkout", task.branch)
        elif remote_exists:
            git(cwd, "checkout", "-b", task.branch, f"origin/{task.branch}")
        else:
            git(cwd, "checkout", "-b", task.branch, f"origin/{BASE_BRANCH}")

    if remote_exists:
        git(cwd, "pull", "--ff-only", "origin", task.branch, check=False)
    else:
        git(cwd, "push", "-u", "origin", task.branch)
    return cwd


def done_tasks_on_base(cwd: Path) -> set[str]:
    content = git(cwd, "show", f"origin/{BASE_BRANCH}:specs/tasks_done.txt", check=False)
    return {
        line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")
    }


def in_scope(task: TaskSpec, path: str) -> bool:
    allowed = [*task.allowed_paths, *SCOPE_ALWAYS_ALLOWED, task.state_file]
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
    env = {**os.environ, "ACCEPTANCE_TASKS": task.id, "PYTHONIOENCODING": "utf-8"}
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
    body_file.write_text(body, encoding="utf-8")
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


def run_session(task: TaskSpec, cwd: Path, session: int, prompt: str) -> str:
    log_dir = cwd / ".agent" / "logs" / task.id
    log_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = log_dir / f"session-{session}-prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    log_file = log_dir / f"session-{session}.jsonl"
    env = {**os.environ, "ACCEPTANCE_TASKS": task.id, "PYTHONIOENCODING": "utf-8"}
    cmd = [
        opencode_bin(),
        "run",
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
    try:
        result = run(cmd, cwd, check=False, env=env, timeout=SESSION_TIMEOUT_S)
        output, code = result.stdout, result.returncode
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout if isinstance(exc.stdout, str) else ""
        code = -1
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent loop de uma task spec-driven")
    parser.add_argument("task", help="ID da task, ex.: T01")
    parser.add_argument("--max-sessions", type=int, default=8)
    parser.add_argument("--worktree", action="store_true", help="usar git worktree isolado")
    parser.add_argument("--force", action="store_true", help="ignorar dependências pendentes")
    args = parser.parse_args(argv)

    task = load_spec(args.task)
    number = issue_number(task.id)
    cwd = prepare_workspace(task, args.worktree)
    log(f"{task.id} em {cwd} (branch {task.branch}, issue #{number})")

    missing = [d for d in task.depends_on if d not in done_tasks_on_base(cwd)]
    if missing and not args.force:
        log(f"dependências ainda não mergeadas em {BASE_BRANCH}: {missing}")
        return 3

    set_labels(cwd, number, add=["in-progress"], remove=["blocked", "needs-review"])
    review = pending_review(cwd, number)
    last_report = ""

    for session in range(1, args.max_sessions + 1):
        log(f"iniciando sessão {session}/{args.max_sessions}")
        head_before = git(cwd, "rev-parse", "HEAD")
        final = run_session(
            task, cwd, session, build_prompt(task, number, session, last_report, review)
        )

        reverted = enforce_scope(task, cwd)
        if reverted:
            commit_leftovers(cwd, f"chore({task.id}): runner reverteu alterações fora do escopo")
        commit_leftovers(cwd, f"chore({task.id}): alterações não commitadas da sessão {session}")
        git(cwd, "push", "origin", task.branch, check=False)
        commits = git(cwd, "log", "--oneline", f"{head_before}..HEAD")

        result = run_checks(task, cwd)
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
            done_file = cwd / "specs" / "tasks_done.txt"
            content = done_file.read_text(encoding="utf-8")
            if task.id not in content.split():
                done_file.write_text(content.rstrip("\n") + f"\n{task.id}\n", encoding="utf-8")
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
