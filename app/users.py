"""Usuários, tokens do Google e planilhas (SQLite). Esqueleto: implementação na task T21."""

from dataclasses import dataclass, field


class UserNotFound(Exception):
    pass


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
    def __init__(self, db_path: str, cipher: object, clock: object = None) -> None:
        raise NotImplementedError("T21")
