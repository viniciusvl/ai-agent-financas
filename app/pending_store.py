"""Armazena gastos aguardando confirmação do usuário (SQLite).

Spec: specs/tasks/T05-pending-store.md
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

from app.domain import Expense


@dataclass
class PendingExpense:
    id: str
    chat_id: int
    user_id: int
    expense: Expense
    created_at: float


class PendingStore:
    def __init__(
        self,
        db_path: str,
        ttl_seconds: int = 86400,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self.clock = clock

    def init(self) -> None:
        raise NotImplementedError("T05")

    def save(self, chat_id: int, user_id: int, expense: Expense) -> str:
        raise NotImplementedError("T05")

    def get(self, pending_id: str) -> PendingExpense | None:
        raise NotImplementedError("T05")

    def delete(self, pending_id: str) -> bool:
        raise NotImplementedError("T05")

    def purge_expired(self) -> int:
        raise NotImplementedError("T05")
