---
id: T21
title: Banco de usuários, tokens do Google e planilhas
branch: feature/T21-usuarios-tokens
depends_on: T05
acceptance: tests/acceptance/test_t21_usuarios.py
allowed_paths:
  - app/crypto.py
  - app/users.py
  - app/config.py
  - requirements.txt
  - .env.example
  - tools/gen_encryption_key.py
---
## Contexto

Base do modo multiusuário (login com Google, uma planilha por pessoa). Esta task cria **só a
camada de dados**: três tabelas no mesmo SQLite do `PendingStore` (`settings.db_path`).
Não há chamadas ao Google, rotas web nem mudanças no bot (tasks seguintes).

## Modelo de dados (definido pelo dono)

`users` — uma linha por pessoa do Telegram

| coluna | tipo | regras |
|---|---|---|
| `id_user` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `t_id` | INTEGER | NOT NULL UNIQUE (id do usuário no Telegram) |
| `nome` | TEXT | pode ser nulo |
| `email` | TEXT | pode ser nulo (e-mail da conta Google) |

`sheets` — planilha ligada à pessoa

| coluna | tipo | regras |
|---|---|---|
| `t_id` | INTEGER | PRIMARY KEY, FOREIGN KEY → `users.t_id` ON DELETE CASCADE |
| `sheet_id` | TEXT | NOT NULL |

`tokens` — credenciais do Google

| coluna | tipo | regras |
|---|---|---|
| `t_id` | INTEGER | PRIMARY KEY, FOREIGN KEY → `users.t_id` ON DELETE CASCADE |
| `access_token` | BLOB | pode ser nulo; **cifrado** |
| `refresh_token` | BLOB | NOT NULL; **cifrado** |
| `expires_at` | REAL | pode ser nulo; epoch em que o `access_token` vence |

Tokens **nunca** ficam em texto puro no banco. Ative `PRAGMA foreign_keys = ON` em toda conexão.

## Requisitos

### `app/crypto.py`
- `class CryptoError(Exception)`.
- `class TokenCipher(keys: list[str])`: `cryptography.fernet.MultiFernet` (a primeira chave
  cifra; todas decifram → rotação de chave). Lista vazia ou chave inválida → `ValueError`.
- `encrypt(plain: str) -> bytes` e `decrypt(blob: bytes) -> str`. Falha ao decifrar →
  `CryptoError` **sem** incluir o conteúdo na mensagem.

### `app/users.py`
- `class UserNotFound(Exception)`.
- `@dataclass(frozen=True) User`: `id_user: int`, `t_id: int`, `nome: str | None`,
  `email: str | None`.
- `@dataclass(frozen=True) Tokens`: `access_token: str | None`, `refresh_token: str`,
  `expires_at: float | None`. `repr`/`str` **não** podem mostrar os tokens (use
  `field(repr=False)`).
- `class UserRepository(db_path: str, cipher: TokenCipher, clock=time.time)`:
  - `init()` — cria o diretório e as 3 tabelas (`IF NOT EXISTS`); idempotente.
  - `upsert_user(t_id, nome=None, email=None) -> User` — cria ou atualiza; `id_user` nunca
    muda; argumento `None` **mantém** o valor existente.
  - `get_user(t_id) -> User | None`.
  - `save_tokens(t_id, refresh_token, access_token=None, expires_at=None) -> None` — substitui
    os tokens existentes; usuário inexistente → `UserNotFound`.
  - `get_tokens(t_id) -> Tokens | None` — já decifrados.
  - `update_access_token(t_id, access_token, expires_at) -> None` — mantém o refresh token;
    sem tokens salvos → `UserNotFound`.
  - `set_sheet(t_id, sheet_id) -> None` — cria ou troca; usuário inexistente → `UserNotFound`.
  - `get_sheet(t_id) -> str | None`.
  - `delete_user(t_id) -> bool` — apaga o usuário e (cascata) tokens e planilha; `True` se
    existia.
  - `count_users() -> int`.
- Conexão por operação (`closing(sqlite3.connect(...))`), como em `app/pending_store.py`.

### Configuração
- `app/config.py`: `token_encryption_keys: str = ""` (env `TOKEN_ENCRYPTION_KEYS`; chaves
  Fernet separadas por vírgula). Vazio = modo multiusuário desligado; o app continua subindo.
- `.env.example`: documente `TOKEN_ENCRYPTION_KEYS` e como gerar a chave.
- `tools/gen_encryption_key.py`: imprime uma chave Fernet nova.
- `requirements.txt`: adicione `cryptography>=43`.

## Fora do escopo
OAuth/Google, rotas, comandos do bot, criação de planilha, cotas, `oauth_states`.

## Subtarefas (uma por sessão)

1. `app/crypto.py` + dependência + config/`.env.example`/script da chave.
2. `app/users.py` (tabelas e `UserRepository`).

## Critérios de aceite

- `ACCEPTANCE_TASKS=T21 python -m pytest tests/acceptance/test_t21_usuarios.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente os caminhos permitidos (+ `tests/unit/`).
