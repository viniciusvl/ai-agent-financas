"""Testes unitários da cifra de tokens (T21 — subtarefa 1)."""

import pytest
from cryptography.fernet import Fernet

from app.config import Settings
from app.crypto import CryptoError, TokenCipher
from tools.gen_encryption_key import main as gerar_chave


def nova_chave() -> str:
    return Fernet.generate_key().decode()


def test_cifra_ida_e_volta():
    cipher = TokenCipher([nova_chave()])
    blob = cipher.encrypt("segredo")
    assert isinstance(blob, bytes)
    assert b"segredo" not in blob
    assert cipher.decrypt(blob) == "segredo"


def test_cifra_aceita_bytes_e_str():
    chave = nova_chave()
    blob = TokenCipher([chave]).encrypt("texto")
    assert TokenCipher([chave.encode()]).decrypt(blob) == "texto"


def test_chave_errada_nao_vaza_conteudo():
    blob = TokenCipher([nova_chave()]).encrypt("segredo-xyz")
    with pytest.raises(CryptoError) as exc:
        TokenCipher([nova_chave()]).decrypt(blob)
    assert "segredo-xyz" not in str(exc.value)


def test_volume_desconhecido_nao_vaza_conteudo():
    with pytest.raises(CryptoError) as exc:
        TokenCipher([nova_chave()]).decrypt(b"lixo")
    assert "lixo" not in str(exc.value)


def test_rotacao_de_chave():
    antiga, nova = nova_chave(), nova_chave()
    blob = TokenCipher([antiga]).encrypt("segredo")
    assert TokenCipher([nova, antiga]).decrypt(blob) == "segredo"
    # a primeira chave cifra: o blob novo não abre só com a antiga
    blob_novo = TokenCipher([nova, antiga]).encrypt("depois")
    with pytest.raises(CryptoError):
        TokenCipher([antiga]).decrypt(blob_novo)


@pytest.mark.parametrize("chaves", [[], ["nao-e-chave-fernet"], ["", nova_chave()]])
def test_chaves_invalidas(chaves):
    with pytest.raises(ValueError):
        TokenCipher(chaves)


def test_config_chave_opcional(monkeypatch):
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEYS", raising=False)
    assert Settings(_env_file=None).token_encryption_keys == ""
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEYS", f"{nova_chave()},{nova_chave()}")
    assert "," in Settings(_env_file=None).token_encryption_keys


def test_script_gera_chave_valida(capsys):
    gerar_chave()
    chave = capsys.readouterr().out.strip()
    assert TokenCipher([chave]).decrypt(TokenCipher([chave]).encrypt("ok")) == "ok"
