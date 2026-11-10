import sqlite3
from contextlib import closing

import pytest
from cryptography.fernet import Fernet

from app.config import Settings
from app.crypto import CryptoError, TokenCipher
from app.pending_store import PendingStore
from app.users import Tokens, User, UserNotFound, UserRepository

pytestmark = pytest.mark.task("T21")

REFRESH = "1//refresh-token-secreto-AAA"
ACCESS = "ya29.access-token-secreto-BBB"


def nova_chave() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def repo(tmp_path):
    r = UserRepository(str(tmp_path / "data" / "bot.db"), TokenCipher([nova_chave()]))
    r.init()
    return r


def colunas(db_path, tabela):
    with closing(sqlite3.connect(db_path)) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({tabela})")}


def test_tabelas_e_colunas(repo):
    assert colunas(repo.db_path, "users") == {"id_user", "t_id", "nome", "email"}
    assert colunas(repo.db_path, "sheets") == {"t_id", "sheet_id"}
    assert colunas(repo.db_path, "tokens") == {
        "t_id",
        "access_token",
        "refresh_token",
        "expires_at",
    }


def test_init_idempotente_e_coexiste_com_pending(repo):
    repo.upsert_user(1, "Ana", "ana@x.com")
    repo.init()
    assert repo.get_user(1) is not None
    PendingStore(repo.db_path).init()
    assert repo.get_user(1) is not None


def test_upsert_cria_e_atualiza_sem_mudar_id(repo):
    a = repo.upsert_user(555, "Maria", "maria@x.com")
    assert isinstance(a, User)
    assert (a.t_id, a.nome, a.email) == (555, "Maria", "maria@x.com")
    b = repo.upsert_user(555, nome="Maria Silva")
    assert b.id_user == a.id_user
    assert (b.nome, b.email) == ("Maria Silva", "maria@x.com")
    assert repo.upsert_user(556).id_user != a.id_user
    assert repo.count_users() == 2


def test_get_inexistente(repo):
    assert repo.get_user(999) is None
    assert repo.get_tokens(999) is None
    assert repo.get_sheet(999) is None


def test_tokens_ida_e_volta_cifrados(repo):
    repo.upsert_user(1)
    repo.save_tokens(1, REFRESH, access_token=ACCESS, expires_at=1234.5)
    t = repo.get_tokens(1)
    assert isinstance(t, Tokens)
    assert (t.refresh_token, t.access_token, t.expires_at) == (REFRESH, ACCESS, 1234.5)
    with closing(sqlite3.connect(repo.db_path)) as conn:
        bruto = conn.execute("SELECT access_token, refresh_token FROM tokens").fetchone()
    for blob in bruto:
        assert REFRESH.encode() not in blob and ACCESS.encode() not in blob
    with open(repo.db_path, "rb") as f:
        conteudo = f.read()
    assert REFRESH.encode() not in conteudo and ACCESS.encode() not in conteudo


def test_save_tokens_substitui(repo):
    repo.upsert_user(1)
    repo.save_tokens(1, REFRESH, access_token=ACCESS)
    repo.save_tokens(1, "1//novo")
    t = repo.get_tokens(1)
    assert (t.refresh_token, t.access_token) == ("1//novo", None)


def test_save_tokens_usuario_inexistente(repo):
    with pytest.raises(UserNotFound):
        repo.save_tokens(42, REFRESH)


def test_update_access_token_mantem_refresh(repo):
    repo.upsert_user(1)
    repo.save_tokens(1, REFRESH, access_token=ACCESS, expires_at=1.0)
    repo.update_access_token(1, "ya29.novo", 99.0)
    t = repo.get_tokens(1)
    assert (t.refresh_token, t.access_token, t.expires_at) == (REFRESH, "ya29.novo", 99.0)
    with pytest.raises(UserNotFound):
        repo.update_access_token(2, "x", 1.0)


def test_repr_nao_vaza_tokens(repo):
    repo.upsert_user(1)
    repo.save_tokens(1, REFRESH, access_token=ACCESS)
    t = repo.get_tokens(1)
    texto = repr(t) + str(t)
    assert REFRESH not in texto and ACCESS not in texto


def test_planilha(repo):
    repo.upsert_user(1)
    assert repo.get_sheet(1) is None
    repo.set_sheet(1, "abc123")
    assert repo.get_sheet(1) == "abc123"
    repo.set_sheet(1, "xyz789")
    assert repo.get_sheet(1) == "xyz789"
    with pytest.raises(UserNotFound):
        repo.set_sheet(77, "abc")


def test_usuarios_isolados(repo):
    repo.upsert_user(1)
    repo.upsert_user(2)
    repo.save_tokens(1, "1//um")
    repo.save_tokens(2, "1//dois")
    repo.set_sheet(1, "S1")
    assert repo.get_tokens(1).refresh_token == "1//um"
    assert repo.get_tokens(2).refresh_token == "1//dois"
    assert repo.get_sheet(2) is None


def test_delete_em_cascata(repo):
    repo.upsert_user(1)
    repo.save_tokens(1, REFRESH)
    repo.set_sheet(1, "S1")
    assert repo.delete_user(1) is True
    assert repo.get_user(1) is None
    assert repo.get_tokens(1) is None
    assert repo.get_sheet(1) is None
    assert repo.delete_user(1) is False
    with closing(sqlite3.connect(repo.db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM sheets").fetchone()[0] == 0


def test_cifra_ida_e_volta():
    c = TokenCipher([nova_chave()])
    blob = c.encrypt("segredo")
    assert isinstance(blob, bytes) and b"segredo" not in blob
    assert c.decrypt(blob) == "segredo"


def test_cifra_chave_errada_nao_vaza():
    blob = TokenCipher([nova_chave()]).encrypt("segredo-xyz")
    with pytest.raises(CryptoError) as exc:
        TokenCipher([nova_chave()]).decrypt(blob)
    assert "segredo-xyz" not in str(exc.value)


def test_cifra_rotacao_de_chave():
    antiga, nova = nova_chave(), nova_chave()
    blob = TokenCipher([antiga]).encrypt("segredo")
    assert TokenCipher([nova, antiga]).decrypt(blob) == "segredo"


@pytest.mark.parametrize("chaves", [[], ["nao-e-chave-fernet"]])
def test_cifra_chaves_invalidas(chaves):
    with pytest.raises(ValueError):
        TokenCipher(chaves)


def test_config_chave_opcional(monkeypatch):
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEYS", raising=False)
    assert Settings(_env_file=None).token_encryption_keys == ""
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEYS", "a,b")
    assert Settings(_env_file=None).token_encryption_keys == "a,b"
