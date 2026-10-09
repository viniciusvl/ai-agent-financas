"""Testes de aceite marcados com @pytest.mark.task("Txx") só rodam quando a task está concluída
(existe o marcador specs/done/Txx) ou quando solicitada via ACCEPTANCE_TASKS=T01,T02."""

import os
from pathlib import Path

import pytest

DONE_DIR = Path(__file__).resolve().parents[1] / "specs" / "done"


def _enabled_tasks() -> set[str]:
    enabled = {p.name for p in DONE_DIR.glob("T*") if p.is_file()}
    extra = os.environ.get("ACCEPTANCE_TASKS", "")
    enabled.update(t.strip() for t in extra.split(",") if t.strip())
    return enabled


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    enabled = _enabled_tasks()
    for item in items:
        marker = item.get_closest_marker("task")
        if marker and marker.args[0] not in enabled:
            item.add_marker(pytest.mark.skip(reason=f"task {marker.args[0]} ainda não concluída"))
