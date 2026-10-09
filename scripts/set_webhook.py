"""Registra o webhook do Telegram apontando para o domínio público.

Uso: ``python -m scripts.set_webhook``

Spec: specs/tasks/T09-deploy.md
"""

import argparse
import asyncio
import logging
import sys

from app.config import get_settings
from app.telegram_api import TelegramClient, TelegramError

logger = logging.getLogger(__name__)


async def _register(token: str, url: str, secret: str) -> bool:
    """Registra a URL no Telegram e sempre fecha o cliente."""
    client = TelegramClient(token)
    try:
        return await client.set_webhook(url, secret)
    finally:
        await client.aclose()


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada: registra o webhook e devolve o código de saída."""
    parser = argparse.ArgumentParser(
        description="Registra o webhook do Telegram na URL pública configurada.",
    )
    parser.parse_args(argv)

    settings = get_settings()
    if not settings.public_base_url or not settings.telegram_webhook_secret:
        logger.error("public_base_url e telegram_webhook_secret precisam estar preenchidos no .env")
        return 1

    url = f"{settings.public_base_url.rstrip('/')}/telegram/webhook"
    try:
        asyncio.run(_register(settings.telegram_bot_token, url, settings.telegram_webhook_secret))
    except TelegramError as exc:
        logger.error("Falha ao registrar o webhook: %s", exc)
        return 1

    logger.info("Webhook registrado em %s", url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
