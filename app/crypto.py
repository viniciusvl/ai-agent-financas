"""Cifra de tokens do Google com Fernet (MultiFernet permite rotação de chaves).

A primeira chave da lista cifra; todas decifram. Spec: specs/tasks/T21-usuarios-tokens.md
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class CryptoError(Exception):
    """Falha ao cifrar/decifrar. A mensagem nunca inclui o conteúdo."""


def _as_bytes(key: str | bytes) -> bytes:
    return key.encode() if isinstance(key, str) else key


class TokenCipher:
    """Cifra e decifra tokens com uma lista de chaves Fernet."""

    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise ValueError("TokenCipher exige ao menos uma chave Fernet")
        try:
            self._fernet = MultiFernet([Fernet(_as_bytes(key)) for key in keys])
        except (TypeError, ValueError) as exc:
            raise ValueError("Chave Fernet inválida") from exc

    def encrypt(self, plain: str) -> bytes:
        return self._fernet.encrypt(plain.encode())

    def decrypt(self, blob: bytes) -> str:
        try:
            return self._fernet.decrypt(blob).decode()
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise CryptoError("Não foi possível decifrar o token") from exc
