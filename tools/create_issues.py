"""Cria (uma vez) as issues [Txx] a partir das specs e grava o mapa em specs/issues.json.

Uso: python -m tools.create_issues
"""

import json
import subprocess
import sys

from tools.agent_loop.runner import ROOT, load_spec

ISSUES_FILE = ROOT / "specs" / "issues.json"


def issue_body(task_id: str, mapping: dict[str, int]) -> str:
    spec = load_spec(task_id)
    deps = ", ".join(f"{d} (#{mapping[d]})" if d in mapping else d for d in spec.depends_on)
    header = [
        f"> **Task spec-driven executada por agent loop.** Processo: #1 · "
        f"Spec: `{spec.path.relative_to(ROOT).as_posix()}`",
        "",
        "| | |",
        "|---|---|",
        f"| Branch | `{spec.branch}` → PR para `develop` |",
        f"| Depende de | {deps or '—'} |",
        f"| Teste de aceite | `{spec.acceptance}` |",
        "| Caminhos permitidos | "
        + ", ".join(f"`{p}`" for p in spec.allowed_paths)
        + ", `tests/unit/` |",
        f"| Status/handoff | `{spec.state_file}` |",
        f"| Executar | `python -m tools.agent_loop.runner {spec.id}` |",
        "",
    ]
    footer = [
        "",
        "## Protocolo do loop",
        "Cada sessão do agente `executor` (opencode + `deepseek/deepseek-flash`) começa do zero, "
        "executa **uma** subtarefa, valida, atualiza o status, faz commit + push e comenta "
        "aqui. O runner valida os critérios de aceite após cada sessão e abre o PR quando "
        "tudo passa. O orquestrador (Claude) revisa; correções chegam como comentário "
        "`## 🔍 Revisão — mudanças solicitadas` + label `changes-requested`.",
    ]
    return "\n".join(header) + spec.body + "\n" + "\n".join(footer)


def main() -> int:
    mapping: dict[str, int] = (
        json.loads(ISSUES_FILE.read_text(encoding="utf-8")) if ISSUES_FILE.exists() else {}
    )
    task_ids = sorted(p.name.split("-")[0] for p in (ROOT / "specs" / "tasks").glob("T*.md"))
    for task_id in task_ids:
        if task_id in mapping:
            continue
        spec = load_spec(task_id)
        result = subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--title",
                f"[{task_id}] {spec.title}",
                "--label",
                "task",
                "--label",
                "agent:deepseek",
                "--body",
                issue_body(task_id, mapping),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        url = result.stdout.strip()
        mapping[task_id] = int(url.rstrip("/").split("/")[-1])
        ISSUES_FILE.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
        print(f"{task_id} → {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
