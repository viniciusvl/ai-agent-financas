"""Armazena gastos aguardando confirmação do usuário (SQLite).

Spec: specs/tasks/T05-pending-store.md
"""

import sqlite3
import time
import uuid
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from app.domain import Expense

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS pending (
    id TEXT PRIMARY KEY,
    chat_id INTEGER,
    user_id INTEGER,
    expense_json TEXT,
    created_at REAL
)
"""


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
        parent = Path(self.db_path).parent
        parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(_CREATE_TABLE)

    def save(self, chat_id: int, user_id: int, expense: Expense) -> str:
        pending_id = uuid.uuid4().hex[:12]
        created_at = self.clock()
        expense_json = expense.model_dump_json()
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                "INSERT INTO pending (id, chat_id, user_id, expense_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (pending_id, chat_id, user_id, expense_json, created_at),
            )
        return pending_id

    def get(self, pending_id: str) -> PendingExpense | None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT id, chat_id, user_id, expense_json, created_at FROM pending WHERE id = ?",
                (pending_id,),
            ).fetchone()
        if row is None:
            return None
        created_at = row[4]
        if self.clock() - created_at > self.ttl_seconds:
            return None
        return PendingExpense(
            id=row[0],
            chat_id=row[1],
            user_id=row[2],
            expense=Expense.model_validate_json(row[3]),
            created_at=created_at,
        )

    def delete(self, pending_id: str) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            cursor = conn.execute("DELETE FROM pending WHERE id = ?", (pending_id,))
        return cursor.rowcount > 0

    def purge_expired(self) -> int:
        threshold = self.clock() - self.ttl_seconds
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            cursor = conn.execute("DELETE FROM pending WHERE created_at < ?", (threshold,))
        return cursor.rowcount
