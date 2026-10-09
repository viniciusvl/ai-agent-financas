"""Testes de aceite marcados com @pytest.mark.task("Txx") só rodam quando a task está concluída
(listada em specs/tasks_done.txt) ou quando solicitada via ACCEPTANCE_TASKS=T01,T02."""

import os
from pathlib import Path

import pytest

DONE_FILE = Path(__file__).resolve().parents[1] / "specs" / "tasks_done.txt"


def _enabled_tasks() -> set[str]:
    enabled: set[str] = set()
    if DONE_FILE.exists():
        for line in DONE_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                enabled.add(line)
    extra = os.environ.get("ACCEPTANCE_TASKS", "")
    enabled.update(t.strip() for t in extra.split(",") if t.strip())
    return enabled


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    enabled = _enabled_tasks()
    for item in items:
        marker = item.get_closest_marker("task")
        if marker and marker.args[0] not in enabled:
            item.add_marker(pytest.mark.skip(reason=f"task {marker.args[0]} ainda não concluída"))
