"""Cifra de tokens (Fernet). Esqueleto: implementação na task T21."""


class CryptoError(Exception):
    pass


class TokenCipher:
    def __init__(self, keys: list[str]) -> None:
        raise NotImplementedError("T21")

    def encrypt(self, plain: str) -> bytes:
        raise NotImplementedError("T21")

    def decrypt(self, blob: bytes) -> str:
        raise NotImplementedError("T21")
