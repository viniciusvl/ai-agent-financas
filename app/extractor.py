"""Extração estruturada de gastos a partir de texto livre usando DeepSeek.

Spec: specs/tasks/T04-deepseek-extractor.md
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from openai import AsyncOpenAI

from app.domain import Expense
from app.prompts import EXTRACTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MSG_INVALID_RESPONSE = "Não consegui interpretar essa mensagem como um gasto."
MSG_DEFAULT_NOT_EXPENSE = "Essa mensagem não parece descrever um gasto."


class ExtractionError(Exception):
    """Falha de comunicação com o LLM (rede, autenticação, rate limit...)."""


@dataclass
class ExtractionResult:
    expense: Expense | None = None
    error: str | None = None


class ExpenseExtractor:
    """Extrai um gasto de um texto livre chamando a API do DeepSeek."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        default_currency: str = "CNY",
        client: Any | None = None,
    ) -> None:
        # `client` permite injetar um fake nos testes; em produção, openai.AsyncOpenAI.
        self.model = model
        self.base_url = base_url
        self.default_currency = default_currency
        self.client: Any = (
            client if client is not None else AsyncOpenAI(api_key=api_key, base_url=base_url)
        )

    def _build_messages(self, text: str, today: date) -> list[dict[str, str]]:
        """Monta o system (prompt formatado) e o user (texto original)."""
        system = EXTRACTION_SYSTEM_PROMPT.format(
            today=today.isoformat(), default_currency=self.default_currency
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ]

    async def _call_api(self, messages: list[dict[str, str]]) -> Any:
        """Chama a API do DeepSeek; erros são encadeados em `ExtractionError`."""
        try:
            return await self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=messages,
            )
        except Exception as exc:
            raise ExtractionError("Falha ao consultar a API do DeepSeek") from exc

    async def extract(self, text: str, today: date) -> ExtractionResult:
        if not text or not text.strip():
            return ExtractionResult(error=MSG_DEFAULT_NOT_EXPENSE)

        response = await self._call_api(self._build_messages(text, today))
        # Subtarefa 2 (próxima sessão): parsing robusto do JSON retornado.
        logger.debug("Resposta bruta do DeepSeek: %r", response.choices[0].message.content)
        return ExtractionResult(error=MSG_INVALID_RESPONSE)
