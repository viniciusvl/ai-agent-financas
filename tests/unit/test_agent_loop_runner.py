from pathlib import Path

import pytest

from tools.agent_loop.runner import ROOT, build_prompt, in_scope, load_spec, parse_front_matter

TASK_IDS = [p.name.split("-")[0] for p in sorted((ROOT / "specs" / "tasks").glob("T*.md"))]


def test_parse_front_matter():
    meta, body = parse_front_matter(
        "---\nid: T99\ndepends_on: T01, T02\nallowed_paths:\n  - app/x.py\n  - deploy/\n---\n# Body"
    )
    assert meta == {"id": "T99", "depends_on": "T01, T02", "allowed_paths": ["app/x.py", "deploy/"]}
    assert body == "# Body"


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_all_specs_are_valid(task_id):
    spec = load_spec(task_id)
    assert spec.id == task_id
    assert spec.branch.startswith(f"feature/{task_id}-")
    assert (ROOT / spec.acceptance).exists()
    assert spec.allowed_paths
    assert "## Critérios de aceite" in spec.body
    assert "## Subtarefas" in spec.body
    for dep in spec.depends_on:
        assert dep in TASK_IDS


def test_scope_rules():
    spec = load_spec("T09")
    assert in_scope(spec, "Dockerfile")
    assert in_scope(spec, "deploy/nginx/china-financas-bot.conf")
    assert in_scope(spec, "tests/unit/test_x.py")
    assert in_scope(spec, ".agent/state/T09.md")
    assert not in_scope(spec, ".agent/state/T01.md")
    assert not in_scope(spec, "tests/acceptance/test_t09_deploy.py")
    assert not in_scope(spec, "app/main.py")
    assert not in_scope(spec, "deployx")


def test_build_prompt_includes_review_and_report():
    spec = load_spec("T01")
    prompt = build_prompt(spec, 7, 2, last_report="RELATORIO", review="## 🔍 Revisão\n- corrigir")
    assert "#7" in prompt and "Sessão 2" in prompt
    assert "PRIORIDADE MÁXIMA" in prompt and "corrigir" in prompt
    assert "RELATORIO" in prompt
    assert Path(spec.acceptance).as_posix() in prompt


def test_review_addressed_requires_fix_commit(tmp_path):
    import subprocess

    from tools.agent_loop.runner import review_addressed

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "a").write_text("1")
    git("add", "-A")
    git("commit", "-q", "-m", "chore: base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    spec = load_spec("T08")
    assert review_addressed(spec, tmp_path, base) is False
    (tmp_path / "a").write_text("2")
    git("commit", "-q", "-am", "feat(T08): outra coisa")
    assert review_addressed(spec, tmp_path, base) is False
    (tmp_path / "a").write_text("3")
    git("commit", "-q", "-am", "fix(T08): corrige revisão")
    assert review_addressed(spec, tmp_path, base) is True


def test_watchdog_kills_idle_process(tmp_path):
    import os
    import sys
    import time

    from tools.agent_loop.runner import run_with_watchdog

    script = "import sys, time; print('evento', flush=True); time.sleep(30)"
    start = time.monotonic()
    out, code = run_with_watchdog(
        [sys.executable, "-c", script], tmp_path, dict(os.environ), total_timeout=60, idle_timeout=2
    )
    assert code == -1
    assert "evento" in out
    assert time.monotonic() - start < 15


def test_watchdog_returns_output_and_code(tmp_path):
    import os
    import sys

    from tools.agent_loop.runner import run_with_watchdog

    out, code = run_with_watchdog(
        [sys.executable, "-c", "print('a'); print('b')"],
        tmp_path,
        dict(os.environ),
        total_timeout=60,
        idle_timeout=30,
    )
    assert code == 0
    assert out.splitlines() == ["a", "b"]
