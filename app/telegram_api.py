"""Cliente assíncrono mínimo da Bot API do Telegram.

Spec: specs/tasks/T02-telegram-client.md
"""

import logging
from typing import Any

import httpx

TELEGRAM_BASE_URL = "https://api.telegram.org"

logger = logging.getLogger(__name__)


class TelegramError(Exception):
    """Erro retornado pela Bot API (ok=false) ou falha HTTP."""


def confirmation_keyboard(pending_id: str) -> dict[str, Any]:
    """Teclado inline com os botões Confirmar/Cancelar. Ver spec T02."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Confirmar", "callback_data": f"confirm:{pending_id}"},
                {"text": "❌ Cancelar", "callback_data": f"cancel:{pending_id}"},
            ]
        ]
    }


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
        self._owns_http = http is None
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30)

    async def aclose(self) -> None:
        """Fecha o client HTTP apenas quando ele foi criado internamente."""
        if self._owns_http:
            await self._http.aclose()

    def _method_url(self, method: str) -> str:
        """Monta a URL do método, sem nunca logar o token."""
        return f"{self.base_url}/bot{self.token}/{method}"

    async def _call(self, method: str, payload: dict[str, Any]) -> Any:
        """Executa um método da Bot API e devolve o campo ``result``."""
        try:
            response = await self._http.post(self._method_url(method), json=payload)
            data = response.json()
        except httpx.HTTPError as exc:
            raise TelegramError(f"Falha de rede ao chamar {method}: {exc}") from exc
        except ValueError as exc:
            raise TelegramError(f"Resposta não-JSON do método {method}") from exc

        if not isinstance(data, dict) or not data.get("ok"):
            description = data.get("description") if isinstance(data, dict) else None
            raise TelegramError(description or f"Erro na Bot API ao chamar {method}")
        return data["result"]

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Envia uma mensagem HTML; inclui ``reply_markup`` só se informado."""
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._call("sendMessage", payload)

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Edita o texto de uma mensagem já enviada."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._call("editMessageText", payload)

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> bool:
        """Confirma um callback; inclui ``text`` (toast) só se informado."""
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text is not None:
            payload["text"] = text
        await self._call("answerCallbackQuery", payload)
        return True

    async def download_file(self, file_id: str) -> bytes:
        """Baixa o conteúdo de um arquivo pelo ``file_id``. Ver spec T02."""
        file_info = await self._call("getFile", {"file_id": file_id})
        file_path = file_info["file_path"]
        url = f"{self.base_url}/file/bot{self.token}/{file_path}"
        try:
            response = await self._http.get(url)
        except httpx.HTTPError as exc:
            raise TelegramError(f"Falha de rede ao baixar arquivo: {exc}") from exc
        if not response.is_success:
            raise TelegramError(f"Falha ao baixar arquivo (status {response.status_code})")
        return response.content

    async def set_webhook(self, url: str, secret_token: str) -> bool:
        """Registra o webhook para atualizações de mensagem e callback."""
        payload = {
            "url": url,
            "secret_token": secret_token,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": False,
        }
        await self._call("setWebhook", payload)
        return True
