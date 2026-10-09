---
id: T09
title: Deploy na EC2 (Docker, Nginx/HTTPS, set_webhook, documentação)
branch: feature/T09-deploy
depends_on: T08
acceptance: tests/acceptance/test_t09_deploy.py
allowed_paths:
  - Dockerfile
  - .dockerignore
  - docker-compose.yml
  - deploy/
  - docs/deploy.md
  - scripts/set_webhook.py
---
## Contexto

A aplicação roda numa EC2 (Ubuntu) com domínio próprio (ainda a ser criado — use o
placeholder `bot.SEU-DOMINIO.com`). Nginx termina TLS (Let's Encrypt/certbot) e faz proxy
para o container em `127.0.0.1:8000`.

## Requisitos

- **Dockerfile**: `FROM python:3.12-slim`; instala `requirements.txt` (sem cache); copia
  `app/`, `scripts/` e `config/`; cria usuário não-root (`USER app`); `EXPOSE 8000`;
  `CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000"]`.
- **.dockerignore**: `.env`, `.git`, `secrets`, `data`, `tests`, `.venv`, `__pycache__`, `.agent`.
- **docker-compose.yml**: serviço `bot` com `build: .`, `env_file: .env`,
  `ports: ["127.0.0.1:8000:8000"]`, volumes `./data:/app/data`,
  `./secrets:/app/secrets:ro` e `./config:/app/config:ro` (editar o formato da planilha sem rebuild), `restart: unless-stopped` e `healthcheck` chamando
  `http://127.0.0.1:8000/health` (com python/urllib — a imagem slim não tem curl).
- **deploy/nginx/china-financas-bot.conf**: server 80 → `return 301 https://$host$request_uri`
  (exceto `/.well-known/acme-challenge/`); server `listen 443 ssl` com `server_name`,
  certificados do Let's Encrypt, `location /telegram/webhook` e `location /health` com
  `proxy_pass http://127.0.0.1:8000`; qualquer outra rota → 404.
- **scripts/set_webhook.py**: `main(argv=None) -> int` com `argparse` (descrição menciona
  "webhook"); importa no nível do módulo `TelegramClient` e `get_settings`; erro (retorna 1)
  se `public_base_url` ou `telegram_webhook_secret` vazios; chama
  `set_webhook(f"{public_base_url}/telegram/webhook", secret)` com `asyncio.run` e fecha o
  cliente com `aclose()`; `if __name__ == "__main__": sys.exit(main())`.
- **docs/deploy.md** (passo a passo, PT-BR) com as seções exatas:
  `## 1. EC2`, `## 2. DNS`, `## 3. Docker`, `## 4. Nginx e HTTPS` (com certbot),
  `## 5. Google Sheets` (service account, compartilhar a planilha com o e-mail dela),
  `## 6. Variáveis de ambiente`, `## 7. Registrar o webhook`, `## 8. Atualizar a aplicação`.

## Subtarefas (uma por sessão)

1. Dockerfile, .dockerignore, docker-compose.yml.
2. Config do Nginx.
3. `scripts/set_webhook.py`.
4. `docs/deploy.md`.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T09 python -m pytest tests/acceptance/test_t09_deploy.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente os caminhos permitidos (+ `tests/unit/`).

## Fora de escopo

Terraform/IaC, CI/CD de deploy automático.
