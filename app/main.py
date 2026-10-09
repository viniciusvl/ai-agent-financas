"""Aplicação FastAPI que recebe o webhook do Telegram.

Rodar: uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8000
Spec: specs/tasks/T08-webhook-app.md
"""

from typing import Any, Protocol

from fastapi import FastAPI

from app.config import Settings

WEBHOOK_PATH = "/telegram/webhook"
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


class UpdateHandler(Protocol):
    async def handle_update(self, update: dict[str, Any]) -> None: ...


def build_service(settings: Settings) -> UpdateHandler:
    """Monta o BotService real com todas as dependências. Ver spec T08."""
    raise NotImplementedError("T08")


def create_app(settings: Settings | None = None, service: UpdateHandler | None = None) -> FastAPI:
    raise NotImplementedError("T08")
