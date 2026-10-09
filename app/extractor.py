"""Extração estruturada de gastos a partir de texto livre usando DeepSeek.

Spec: specs/tasks/T04-deepseek-extractor.md
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain import Expense

MSG_INVALID_RESPONSE = "Não consegui interpretar essa mensagem como um gasto."
MSG_DEFAULT_NOT_EXPENSE = "Essa mensagem não parece descrever um gasto."


class ExtractionError(Exception):
    """Falha de comunicação com o LLM (rede, autenticação, rate limit...)."""


@dataclass
class ExtractionResult:
    expense: Expense | None = None
    error: str | None = None


class ExpenseExtractor:
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        default_currency: str = "CNY",
        client: Any | None = None,
    ) -> None:
        # `client` permite injetar um fake nos testes; em produção, openai.AsyncOpenAI.
        raise NotImplementedError("T04")

    async def extract(self, text: str, today: date) -> ExtractionResult:
        raise NotImplementedError("T04")
