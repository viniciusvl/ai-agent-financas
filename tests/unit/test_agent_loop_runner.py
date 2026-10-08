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
