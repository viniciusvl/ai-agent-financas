"""Usuários, tokens do Google e planilhas (SQLite).

Tokens são sempre cifrados com `TokenCipher`. Spec: specs/tasks/T21-usuarios-tokens.md
"""

import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

from app.crypto import TokenCipher

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id_user INTEGER PRIMARY KEY AUTOINCREMENT,
    t_id INTEGER NOT NULL UNIQUE,
    nome TEXT,
    email TEXT
)
"""

_CREATE_SHEETS = """
CREATE TABLE IF NOT EXISTS sheets (
    t_id INTEGER PRIMARY KEY REFERENCES users(t_id) ON DELETE CASCADE,
    sheet_id TEXT NOT NULL
)
"""

_CREATE_TOKENS = """
CREATE TABLE IF NOT EXISTS tokens (
    t_id INTEGER PRIMARY KEY REFERENCES users(t_id) ON DELETE CASCADE,
    access_token BLOB,
    refresh_token BLOB NOT NULL,
    expires_at REAL
)
"""


class UserNotFound(Exception):
    """Usuário inexistente (ou sem tokens salvos, quando aplicável)."""


@dataclass(frozen=True)
class User:
    id_user: int
    t_id: int
    nome: str | None
    email: str | None


@dataclass(frozen=True)
class Tokens:
    refresh_token: str = field(repr=False)
    access_token: str | None = field(default=None, repr=False)
    expires_at: float | None = None


class UserRepository:
    """Acesso às tabelas `users`, `sheets` e `tokens` no SQLite do app."""

    def __init__(
        self,
        db_path: str,
        cipher: TokenCipher,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db_path = db_path
        self.cipher = cipher
        self.clock = clock

    def init(self) -> None:
        """Cria o diretório e as tabelas (idempotente)."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.execute(_CREATE_USERS)
            conn.execute(_CREATE_SHEETS)
            conn.execute(_CREATE_TOKENS)

    def upsert_user(
        self,
        t_id: int,
        nome: str | None = None,
        email: str | None = None,
    ) -> User:
        """Cria ou atualiza o usuário; `None` mantém o valor existente."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO users (t_id, nome, email) VALUES (?, ?, ?) "
                "ON CONFLICT(t_id) DO UPDATE SET "
                "nome = COALESCE(excluded.nome, users.nome), "
                "email = COALESCE(excluded.email, users.email)",
                (t_id, nome, email),
            )
            row = conn.execute(
                "SELECT id_user, t_id, nome, email FROM users WHERE t_id = ?",
                (t_id,),
            ).fetchone()
        return User(*row)

    def get_user(self, t_id: int) -> User | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id_user, t_id, nome, email FROM users WHERE t_id = ?",
                (t_id,),
            ).fetchone()
        return None if row is None else User(*row)

    def save_tokens(
        self,
        t_id: int,
        refresh_token: str,
        access_token: str | None = None,
        expires_at: float | None = None,
    ) -> None:
        """Substitui os tokens do usuário."""
        refresh_blob = self.cipher.encrypt(refresh_token)
        access_blob = None if access_token is None else self.cipher.encrypt(access_token)
        with closing(self._connect()) as conn, conn:
            self._require_user(conn, t_id)
            conn.execute(
                "INSERT INTO tokens (t_id, access_token, refresh_token, expires_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(t_id) DO UPDATE SET "
                "access_token = excluded.access_token, "
                "refresh_token = excluded.refresh_token, "
                "expires_at = excluded.expires_at",
                (t_id, access_blob, refresh_blob, expires_at),
            )

    def get_tokens(self, t_id: int) -> Tokens | None:
        """Tokens já decifrados, ou `None` se não houver."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT access_token, refresh_token, expires_at FROM tokens WHERE t_id = ?",
                (t_id,),
            ).fetchone()
        if row is None:
            return None
        access_blob, refresh_blob, expires_at = row
        return Tokens(
            refresh_token=self.cipher.decrypt(refresh_blob),
            access_token=None if access_blob is None else self.cipher.decrypt(access_blob),
            expires_at=expires_at,
        )

    def update_access_token(
        self,
        t_id: int,
        access_token: str,
        expires_at: float | None,
    ) -> None:
        """Atualiza o access token, mantendo o refresh token."""
        access_blob = self.cipher.encrypt(access_token)
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT 1 FROM tokens WHERE t_id = ?", (t_id,)).fetchone()
            if row is None:
                raise UserNotFound(f"Tokens não encontrados para o usuário {t_id}")
            conn.execute(
                "UPDATE tokens SET access_token = ?, expires_at = ? WHERE t_id = ?",
                (access_blob, expires_at, t_id),
            )

    def set_sheet(self, t_id: int, sheet_id: str) -> None:
        """Cria ou troca a planilha do usuário."""
        with closing(self._connect()) as conn, conn:
            self._require_user(conn, t_id)
            conn.execute(
                "INSERT INTO sheets (t_id, sheet_id) VALUES (?, ?) "
                "ON CONFLICT(t_id) DO UPDATE SET sheet_id = excluded.sheet_id",
                (t_id, sheet_id),
            )

    def get_sheet(self, t_id: int) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT sheet_id FROM sheets WHERE t_id = ?",
                (t_id,),
            ).fetchone()
        return None if row is None else row[0]

    def delete_user(self, t_id: int) -> bool:
        """Apaga o usuário e, em cascata, tokens e planilha."""
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute("DELETE FROM users WHERE t_id = ?", (t_id,))
        return cursor.rowcount > 0

    def count_users(self) -> int:
        with closing(self._connect()) as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _require_user(conn: sqlite3.Connection, t_id: int) -> None:
        row = conn.execute("SELECT 1 FROM users WHERE t_id = ?", (t_id,)).fetchone()
        if row is None:
            raise UserNotFound(f"Usuário {t_id} não encontrado")
