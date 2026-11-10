"""Testes unitários do repositório de usuários (T21 — subtarefa 2)."""

import sqlite3
from contextlib import closing

import pytest
from cryptography.fernet import Fernet

from app.crypto import TokenCipher
from app.users import Tokens, User, UserNotFound, UserRepository


@pytest.fixture
def repo(tmp_path):
    cipher = TokenCipher([Fernet.generate_key().decode()])
    r = UserRepository(str(tmp_path / "data" / "bot.db"), cipher)
    r.init()
    return r


def test_init_cria_diretorio_e_e_idempotente(repo):
    repo.init()
    assert repo.count_users() == 0
    assert repo.get_user(1) is None


def test_upsert_mantem_valores_quando_none(repo):
    original = repo.upsert_user(10, "Ana", "ana@x.com")
    apenas_email = repo.upsert_user(10, email="nova@x.com")
    assert (apenas_email.id_user, apenas_email.nome, apenas_email.email) == (
        original.id_user,
        "Ana",
        "nova@x.com",
    )
    so_nome = repo.upsert_user(10, nome="Ana Maria")
    assert (so_nome.nome, so_nome.email) == ("Ana Maria", "nova@x.com")


def test_save_tokens_sem_access_token(repo):
    repo.upsert_user(1)
    repo.save_tokens(1, "refresh")
    tokens = repo.get_tokens(1)
    assert isinstance(tokens, Tokens)
    assert (tokens.refresh_token, tokens.access_token, tokens.expires_at) == ("refresh", None, None)


def test_tokens_brutos_nao_ficam_em_texto_puro(repo):
    repo.upsert_user(1)
    repo.save_tokens(1, "refresh-secreto", access_token="access-secreto")
    with closing(sqlite3.connect(repo.db_path)) as conn:
        rows = conn.execute("SELECT access_token, refresh_token FROM tokens").fetchall()
    for blob in rows[0]:
        assert b"refresh-secreto" not in blob
        assert b"access-secreto" not in blob


def test_foreign_keys_ligadas(repo):
    with pytest.raises(sqlite3.IntegrityError):
        with closing(sqlite3.connect(repo.db_path)) as conn, conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("INSERT INTO sheets (t_id, sheet_id) VALUES (1, 'S1')")


def test_delete_usuario_sem_dados(repo):
    user = repo.upsert_user(7)
    assert isinstance(user, User)
    assert repo.delete_user(7) is True
    assert repo.delete_user(7) is False
    assert repo.count_users() == 0


def test_update_access_token_exige_tokens(repo):
    repo.upsert_user(1)
    with pytest.raises(UserNotFound):
        repo.update_access_token(1, "novo", 1.0)
