"""Aplicação FastAPI que recebe o webhook do Telegram.

Rodar: uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8000
Spec: specs/tasks/T08-webhook-app.md
"""

import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from app.config import Settings, get_settings

WEBHOOK_PATH = "/telegram/webhook"
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


class UpdateHandler(Protocol):
    async def handle_update(self, update: dict[str, Any]) -> None: ...


def build_service(settings: Settings) -> UpdateHandler:
    """Monta o BotService real com todas as dependências. Ver spec T08."""
    raise NotImplementedError("T08")


def create_app(settings: Settings | None = None, service: UpdateHandler | None = None) -> FastAPI:
    """Cria a aplicação FastAPI do webhook do Telegram. Ver spec T08."""
    settings = settings or get_settings()
    if not settings.telegram_webhook_secret:
        raise ValueError("telegram_webhook_secret não configurado")
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        handler = service if service is not None else build_service(settings)
        app.state.service = handler
        try:
            yield
        finally:
            if service is None:
                await _close_handler(handler)

    app = FastAPI(title="china-financas-bot", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(WEBHOOK_PATH)
    async def telegram_webhook(
        request: Request, background_tasks: BackgroundTasks
    ) -> dict[str, bool]:
        provided = request.headers.get(SECRET_HEADER, "")
        if not secrets.compare_digest(provided, settings.telegram_webhook_secret):
            raise HTTPException(status_code=403, detail="forbidden")
        update = await request.json()
        background_tasks.add_task(app.state.service.handle_update, update)
        return {"ok": True}

    return app


async def _close_handler(handler: Any) -> None:
    """Fecha dependências que expõem ``aclose`` (ex.: TelegramClient)."""
    aclose = getattr(handler, "aclose", None)
    if aclose is not None:
        await aclose()
