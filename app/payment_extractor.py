"""Extração de pagamentos (intenção "escrita", v2) com DeepSeek.

O LLM extrai os campos; data/hora padrão vêm do timestamp da mensagem e o valor das parcelas é
calculado pela aplicação (app/payment.py). Spec: specs/tasks/T13-payment-extractor.md
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI

from app.extractor import MSG_DEFAULT_NOT_EXPENSE, MSG_INVALID_RESPONSE, ExtractionError
from app.payment import Pagamento
from app.prompts import PAYMENT_EXTRACTION_SYSTEM_PROMPT
from app.sheet_schema import SheetSchema

logger = logging.getLogger(__name__)

__all__ = [
    "MSG_DEFAULT_NOT_EXPENSE",
    "MSG_INVALID_RESPONSE",
    "ExtractionError",
    "PaymentExtractor",
    "ResultadoExtracao",
]


@dataclass
class ResultadoExtracao:
    pagamento: Pagamento | None = None
    pergunta: str | None = None  # dado obrigatório faltando: o bot pergunta ao usuário
    erro: str | None = None  # não é pagamento ou resposta inválida


class PaymentExtractor:
    """Extrai um pagamento de um texto livre chamando a API do DeepSeek."""

    def __init__(
        self,
        api_key: str,
        schema: SheetSchema,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        default_currency: str = "CNY",
        timezone: str = "Asia/Shanghai",
        client: Any | None = None,
    ) -> None:
        # `client` permite injetar um fake nos testes; em produção, openai.AsyncOpenAI.
        self.model = model
        self.base_url = base_url
        self.schema = schema
        self.default_currency = default_currency
        self.timezone = timezone
        self.client: Any = (
            client if client is not None else AsyncOpenAI(api_key=api_key, base_url=base_url)
        )

    def _build_messages(self, texto: str, local: datetime) -> list[dict[str, str]]:
        """Monta o system (prompt formatado) e o user (texto original exato)."""
        system = PAYMENT_EXTRACTION_SYSTEM_PROMPT.format(
            agora=local.strftime("%H:%M"),
            hoje=local.date().isoformat(),
            moeda_padrao=self.default_currency,
            schema=self.schema.prompt_context(),
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": texto},
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

    async def extract(self, texto: str, recebido_em: datetime) -> ResultadoExtracao:
        if not texto or not texto.strip():
            return ResultadoExtracao(erro=MSG_DEFAULT_NOT_EXPENSE)

        local = recebido_em.astimezone(ZoneInfo(self.timezone))
        response = await self._call_api(self._build_messages(texto, local))
        logger.debug("Resposta bruta do DeepSeek: %r", response)
        # TODO(T13, subtarefa 2): parse robusto da resposta e tratamento de `is_pagamento`.
        return ResultadoExtracao()
