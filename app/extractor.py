"""Extração estruturada de gastos a partir de texto livre usando DeepSeek.

Spec: specs/tasks/T04-deepseek-extractor.md
"""

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

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


def _strip_code_fences(content: str) -> str:
    """Remove cercas de código Markdown (```json ... ```), se existirem."""
    text = content.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_payload(content: object) -> dict[str, Any] | None:
    """Converte o conteúdo do LLM em objeto JSON; inválido/não-objeto vira `None`."""
    if not isinstance(content, str):
        return None
    text = _strip_code_fences(content)
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _parse_spent_at(value: object, today: date) -> date:
    """Interpreta a data ISO; qualquer valor inválido recai em `today`."""
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return today
    if isinstance(value, date):
        return value
    return today


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
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.default_currency = default_currency
        self.client = (
            client if client is not None else AsyncOpenAI(api_key=api_key, base_url=base_url)
        )

    async def extract(self, text: str, today: date) -> ExtractionResult:
        """Transforma o texto livre em um `Expense` (ou em uma mensagem de erro)."""
        if not text or not text.strip():
            return ExtractionResult(error=MSG_DEFAULT_NOT_EXPENSE)

        system_prompt = EXTRACTION_SYSTEM_PROMPT.format(
            today=today.isoformat(), default_currency=self.default_currency
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
            )
        except Exception as exc:  # noqa: BLE001 - vira erro de domínio encadeado
            logger.warning("Falha ao chamar o DeepSeek: %s", type(exc).__name__)
            raise ExtractionError("Falha ao consultar o DeepSeek.") from exc

        content = response.choices[0].message.content
        data = _parse_payload(content)
        if data is None:
            return ExtractionResult(error=MSG_INVALID_RESPONSE)

        if not data.get("is_expense"):
            reason = data.get("reason")
            return ExtractionResult(error=reason or MSG_DEFAULT_NOT_EXPENSE)

        try:
            expense = Expense(
                amount=data.get("amount"),
                currency=data.get("currency") or self.default_currency,
                category=data.get("category"),
                description=data.get("description"),
                payment_method=data.get("payment_method"),
                spent_at=_parse_spent_at(data.get("date"), today),
                raw_text=text,
            )
        except ValidationError:
            return ExtractionResult(error=MSG_INVALID_RESPONSE)

        return ExtractionResult(expense=expense)
