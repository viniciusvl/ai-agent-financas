"""Gera uma chave Fernet para TOKEN_ENCRYPTION_KEYS.

Uso: python -m tools.gen_encryption_key
"""

from cryptography.fernet import Fernet


def main() -> None:
    print(Fernet.generate_key().decode())


if __name__ == "__main__":
    main()
