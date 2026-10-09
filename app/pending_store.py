"""Armazena gastos aguardando confirmação do usuário (SQLite).

Spec: specs/tasks/T05-pending-store.md
"""

import os
import sqlite3
import time
import uuid
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
        """Cria o diretório pai e a tabela `pending`; idempotente.

        Spec: specs/tasks/T05-pending-store.md
        """
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending (
                    id TEXT PRIMARY KEY,
                    chat_id INTEGER,
                    user_id INTEGER,
                    expense_json TEXT,
                    created_at REAL
                )
                """
            )

    def save(self, chat_id: int, user_id: int, expense: Expense) -> str:
        """Persiste um gasto pendente e devolve o id gerado.

        Spec: specs/tasks/T05-pending-store.md
        """
        pending_id = uuid.uuid4().hex[:12]
        created_at = self.clock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO pending (id, chat_id, user_id, expense_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (pending_id, chat_id, user_id, expense.model_dump_json(), created_at),
            )
        return pending_id

    def get(self, pending_id: str) -> PendingExpense | None:
        """Recupera um gasto pendente pelo id; `None` se não existir.

        Spec: specs/tasks/T05-pending-store.md
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, chat_id, user_id, expense_json, created_at FROM pending WHERE id = ?",
                (pending_id,),
            ).fetchone()
        if row is None:
            return None
        return PendingExpense(
            id=row[0],
            chat_id=row[1],
            user_id=row[2],
            expense=Expense.model_validate_json(row[3]),
            created_at=row[4],
        )

    def delete(self, pending_id: str) -> bool:
        raise NotImplementedError("T05")

    def purge_expired(self) -> int:
        raise NotImplementedError("T05")
