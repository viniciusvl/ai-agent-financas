"""Aplicação FastAPI que recebe o webhook do Telegram.

Rodar: uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8000
Spec: specs/tasks/T08-webhook-app.md
"""

import json
import logging
import secrets
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from app.config import Settings, get_settings

WEBHOOK_PATH = "/telegram/webhook"
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
MAX_SEEN_UPDATE_IDS = 1000


class UpdateHandler(Protocol):
    async def handle_update(self, update: dict[str, Any]) -> None: ...


def build_service(settings: Settings) -> UpdateHandler:
    """Monta o BotService real com todas as dependências. Ver spec T08."""
    from app.bot import BotService
    from app.payment import Pagamento
    from app.payment_extractor import PaymentExtractor
    from app.pending_store import PendingStore
    from app.queries import GastosRepository
    from app.read_agent import ReadAgent
    from app.router import DeepSeekIntentFallback, IntentRouter
    from app.sheet_schema import SheetSchema
    from app.sheets import PagamentoSheetWriter
    from app.stt import WhisperTranscriber
    from app.telegram_api import TelegramClient

    schema = SheetSchema.load(settings.sheet_schema_path)
    telegram = TelegramClient(settings.telegram_bot_token)
    transcriber = WhisperTranscriber(
        api_key=settings.whisper_api_key,
        model=settings.whisper_model,
        language=settings.whisper_language,
        base_url=settings.whisper_base_url,
    )
    fallback = DeepSeekIntentFallback(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
    )
    router = IntentRouter(
        api_key=settings.typesafe_api_key,
        model=settings.jev_model,
        base_url=settings.jev_base_url,
        threshold=settings.router_confidence_threshold,
        fallback=fallback,
    )
    extractor = PaymentExtractor(
        api_key=settings.deepseek_api_key,
        schema=schema,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        default_currency=settings.default_currency,
        timezone=settings.timezone,
    )
    writer = PagamentoSheetWriter.from_service_account(
        settings.google_service_account_file, settings.google_sheet_id, schema
    )
    read_agent = ReadAgent(
        api_key=settings.deepseek_api_key,
        repo=GastosRepository(writer.worksheet, schema),
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        timezone=settings.timezone,
    )
    store = PendingStore(settings.db_path, settings.pending_ttl_seconds, model=Pagamento)
    store.init()
    return BotService(
        telegram,
        transcriber,
        router,
        extractor,
        read_agent,
        store,
        writer,
        allowed_user_ids=set(settings.allowed_user_ids),
        timezone=settings.timezone,
    )


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

    seen_update_ids: set[int] = set()
    recent_update_ids: deque[int] = deque(maxlen=MAX_SEEN_UPDATE_IDS)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(WEBHOOK_PATH)
    async def telegram_webhook(
        request: Request, background_tasks: BackgroundTasks
    ) -> dict[str, bool]:
        provided = request.headers.get(SECRET_HEADER, "")
        # Comparar bytes: ``compare_digest`` com ``str`` exige ASCII e levantaria
        # ``TypeError`` (500) para um header com caractere não-ASCII controlado
        # pelo chamador. Ver revisão da T08.
        if not secrets.compare_digest(
            provided.encode("utf-8"), settings.telegram_webhook_secret.encode("utf-8")
        ):
            raise HTTPException(status_code=403, detail="forbidden")
        try:
            update = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="invalid json") from exc
        if not isinstance(update, dict):
            raise HTTPException(status_code=400, detail="invalid update")
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            if update_id in seen_update_ids:
                return {"ok": True}
            if len(recent_update_ids) == recent_update_ids.maxlen:
                seen_update_ids.discard(recent_update_ids[0])
            recent_update_ids.append(update_id)
            seen_update_ids.add(update_id)
        background_tasks.add_task(app.state.service.handle_update, update)
        return {"ok": True}

    return app


async def _close_handler(handler: Any) -> None:
    """Fecha as dependências com ``aclose`` (TelegramClient e IntentRouter)."""
    for dependencia in (getattr(handler, "telegram", None), getattr(handler, "router", None)):
        aclose = getattr(dependencia, "aclose", None)
        if aclose is not None:
            await aclose()
    aclose = getattr(handler, "aclose", None)
    if aclose is not None:
        await aclose()
