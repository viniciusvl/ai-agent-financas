"""Extração estruturada de gastos a partir de texto livre usando DeepSeek.

Spec: specs/tasks/T04-deepseek-extractor.md
"""

import json
import logging
import re
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

# Cerca de código markdown: ```json\n...\n``` (a linguagem é opcional).
_CODE_FENCE_RE = re.compile(r"^```[A-Za-z0-9_-]*\s*\n?(.*?)\n?```$", re.DOTALL)


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

    @staticmethod
    def _content_from_response(response: Any) -> Any:
        """Extrai `choices[0].message.content` de forma defensiva.

        Respostas sem `choices`, lista vazia, sem `message` ou sem `content`
        retornam `None` (echo downstream vira `MSG_INVALID_RESPONSE`).
        """
        try:
            choice = response.choices[0]
            return choice.message.content
        except (AttributeError, IndexError, KeyError, TypeError):
            return None

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        """Remove cercas de código markdown (```json … ```) ao redor do JSON."""
        text = content.strip()
        match = _CODE_FENCE_RE.match(text)
        if match:
            return match.group(1).strip()
        return text

    def _parse_content(self, content: Any) -> dict[str, Any] | None:
        """Interpreta o conteúdo bruto do LLM como objeto JSON, ou `None` se inválido."""
        if not isinstance(content, str):
            return None
        text = self._strip_code_fence(content)
        if not text:
            return None
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        return data

    async def extract(self, text: str, today: date) -> ExtractionResult:
        if not text or not text.strip():
            return ExtractionResult(error=MSG_DEFAULT_NOT_EXPENSE)

        response = await self._call_api(self._build_messages(text, today))
        content = self._content_from_response(response)
        logger.debug("Resposta bruta do DeepSeek: %r", content)

        data = self._parse_content(content)
        if data is None:
            return ExtractionResult(error=MSG_INVALID_RESPONSE)

        if not data.get("is_expense"):
            reason = data.get("reason") or MSG_DEFAULT_NOT_EXPENSE
            return ExtractionResult(error=reason)

        try:
            expense = Expense(
                amount=data.get("amount"),
                currency=self._resolve_currency(data.get("currency")),
                category=data.get("category"),
                description=data.get("description"),
                payment_method=data.get("payment_method"),
                spent_at=self._resolve_date(data.get("date"), today),
                raw_text=text,
            )
        except ValidationError:
            return ExtractionResult(error=MSG_INVALID_RESPONSE)

        return ExtractionResult(expense=expense)

    def _resolve_currency(self, value: Any) -> Any:
        """Usa a moeda retornada pelo LLM ou a padrão quando ausente."""
        return self.default_currency if value is None else value

    @staticmethod
    def _resolve_date(value: Any, today: date) -> date:
        """Interpreta a data ISO retornada pelo LLM; inválida cai em `today`."""
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip())
            except ValueError:
                return today
        return today
