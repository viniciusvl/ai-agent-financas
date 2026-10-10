import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("T09")

ROOT = Path(__file__).resolve().parents[2]


def read(rel):
    path = ROOT / rel
    assert path.exists(), f"{rel} não existe"
    return path.read_text(encoding="utf-8")


def test_dockerfile():
    content = read("Dockerfile")
    assert "FROM python:3.12-slim" in content
    assert "requirements.txt" in content
    assert "config" in content, "a imagem precisa do config/planilha.yaml"
    assert "EXPOSE 8000" in content
    assert "--factory" in content and "app.main:create_app" in content
    assert "USER " in content, "o container não deve rodar como root"


def test_dockerignore():
    content = read(".dockerignore")
    for entry in (".env", ".git", "secrets", "data", "tests"):
        assert entry in content


def test_compose():
    content = read("docker-compose.yml")
    assert "127.0.0.1:8000:8000" in content
    assert "env_file" in content and ".env" in content
    assert "./data:/app/data" in content
    assert "./secrets:/app/secrets:ro" in content
    assert "./config:/app/config:ro" in content
    assert "restart: unless-stopped" in content
    assert "healthcheck" in content and "/health" in content


def test_nginx_config():
    confs = [p for p in (ROOT / "deploy" / "nginx").glob("*.conf") if "http-only" not in p.name]
    assert len(confs) == 1, "uma config completa do Nginx em deploy/nginx/"
    content = confs[0].read_text(encoding="utf-8")
    assert "server_name" in content
    assert "location /telegram/webhook" in content
    assert "location /health" in content
    assert "proxy_pass http://127.0.0.1:8000" in content
    assert "listen 443 ssl" in content
    assert "return 301 https://" in content


def test_deploy_doc_sections():
    content = read("docs/deploy.md")
    for section in (
        "## 1. EC2",
        "## 2. DNS",
        "## 3. Docker",
        "## 4. Nginx e HTTPS",
        "## 5. Google Sheets",
        "## 6. Variáveis de ambiente",
        "## 7. Registrar o webhook",
        "## 8. Atualizar a aplicação",
    ):
        assert section in content, f"seção ausente: {section}"
    assert "certbot" in content


def test_set_webhook_help():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.set_webhook", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert "webhook" in result.stdout.lower()


def test_set_webhook_main_calls_telegram(monkeypatch):
    from app.config import Settings
    from scripts import set_webhook

    calls = []

    class FakeClient:
        def __init__(self, token):
            calls.append(("init", token))

        async def set_webhook(self, url, secret_token):
            calls.append(("set_webhook", url, secret_token))
            return True

        async def aclose(self):
            calls.append(("aclose",))

    monkeypatch.setattr(set_webhook, "TelegramClient", FakeClient)
    monkeypatch.setattr(
        set_webhook,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            telegram_bot_token="123:ABC",
            telegram_webhook_secret="sec",
            public_base_url="https://bot.example.com/",
        ),
    )
    assert set_webhook.main([]) == 0
    assert calls == [
        ("init", "123:ABC"),
        ("set_webhook", "https://bot.example.com/telegram/webhook", "sec"),
        ("aclose",),
    ]


def test_set_webhook_requires_public_url(monkeypatch):
    from app.config import Settings
    from scripts import set_webhook

    monkeypatch.setattr(
        set_webhook,
        "get_settings",
        lambda: Settings(_env_file=None, telegram_bot_token="t", telegram_webhook_secret="s"),
    )
    assert set_webhook.main([]) != 0
