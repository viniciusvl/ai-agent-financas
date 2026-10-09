"""Orquestração do fluxo do bot: mensagem → (STT) → extração → confirmação → planilha.

Spec: specs/tasks/T07-bot-flow.md
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any


class BotService:
    def __init__(
        self,
        telegram: Any,
        transcriber: Any,
        extractor: Any,
        store: Any,
        sheets: Any,
        allowed_user_ids: set[int],
        timezone: str = "Asia/Shanghai",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        raise NotImplementedError("T07")

    async def handle_update(self, update: dict[str, Any]) -> None:
        """Processa um Update do Telegram. Nunca propaga exceções."""
        raise NotImplementedError("T07")
