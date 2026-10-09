"""Cliente assíncrono mínimo da Bot API do Telegram.

Spec: specs/tasks/T02-telegram-client.md
"""

from typing import Any

import httpx

TELEGRAM_BASE_URL = "https://api.telegram.org"


class TelegramError(Exception):
    """Erro retornado pela Bot API (ok=false) ou falha HTTP."""


def confirmation_keyboard(pending_id: str) -> dict[str, Any]:
    """Teclado inline com os botões Confirmar/Cancelar. Ver spec T02."""
    raise NotImplementedError("T02")


class TelegramClient:
    def __init__(
        self,
        token: str,
        http: httpx.AsyncClient | None = None,
        base_url: str = TELEGRAM_BASE_URL,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._http = http
        # TODO(T02): criar AsyncClient próprio quando `http` for None.

    async def aclose(self) -> None:
        raise NotImplementedError("T02")

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        raise NotImplementedError("T02")

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("T02")

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> bool:
        raise NotImplementedError("T02")

    async def download_file(self, file_id: str) -> bytes:
        raise NotImplementedError("T02")

    async def set_webhook(self, url: str, secret_token: str) -> bool:
        raise NotImplementedError("T02")
