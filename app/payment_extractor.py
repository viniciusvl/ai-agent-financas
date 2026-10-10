"""Extração de pagamentos (intenção "escrita", v2) com DeepSeek.

O LLM extrai os campos; data/hora padrão vêm do timestamp da mensagem e o valor das parcelas é
calculado pela aplicação (app/payment.py). Spec: specs/tasks/T13-payment-extractor.md
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.extractor import (
    MSG_DEFAULT_NOT_EXPENSE,
    MSG_INVALID_RESPONSE,
    ExpenseExtractor,
    ExtractionError,
)
from app.messages import MSG_PERGUNTA_PARCELAS, MSG_PERGUNTA_VALOR
from app.payment import MetodoPagamento, Pagamento, normalizar_metodo
from app.prompts import PAYMENT_EXTRACTION_SYSTEM_PROMPT
from app.sheet_schema import SheetSchema

logger = logging.getLogger(__name__)

# Horário no formato HH:MM (hora com 1 ou 2 dígitos, minutos com 2).
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")

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
        default_currency: str = "BRL",
        timezone: str = "America/Sao_Paulo",
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

    @staticmethod
    def _content_from_response(response: Any) -> Any:
        """Extrai `choices[0].message.content` de forma defensiva (reaproveita o extrator v1).

        Respostas sem `choices`, lista vazia, sem `message` ou sem `content` retornam `None`.
        """
        return ExpenseExtractor._content_from_response(response)

    @staticmethod
    def _parse_content(content: Any) -> dict[str, Any] | None:
        """Interpreta o conteúdo do LLM como objeto JSON, ou `None` se inválido.

        Reaproveita a remoção de cercas de código do extrator v1; conteúdo não-string, JSON
        inválido ou que não seja objeto vira `None` (o chamador responde `MSG_INVALID_RESPONSE`).
        """
        if not isinstance(content, str):
            return None
        text = ExpenseExtractor._strip_code_fence(content)
        if not text:
            return None
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    async def extract(self, texto: str, recebido_em: datetime) -> ResultadoExtracao:
        if not texto or not texto.strip():
            return ResultadoExtracao(erro=MSG_DEFAULT_NOT_EXPENSE)

        local = recebido_em.astimezone(ZoneInfo(self.timezone))
        response = await self._call_api(self._build_messages(texto, local))
        content = self._content_from_response(response)
        logger.debug("Resposta bruta do DeepSeek: %r", content)

        data = self._parse_content(content)
        if data is None:
            return ResultadoExtracao(erro=MSG_INVALID_RESPONSE)

        if not data.get("is_pagamento"):
            return ResultadoExtracao(erro=data.get("motivo") or MSG_DEFAULT_NOT_EXPENSE)

        # Passo 7: valor ausente → o bot pergunta ao usuário.
        if data.get("valor_compra") is None:
            return ResultadoExtracao(pergunta=MSG_PERGUNTA_VALOR)

        # Passo 8: compra parcelada sem o número de parcelas → o bot pergunta ao usuário.
        metodo = normalizar_metodo(data.get("metodo_pagamento"))
        quant_parcelas = data.get("quant_parcelas")
        if self._precisa_perguntar_parcelas(metodo, quant_parcelas):
            return ResultadoExtracao(pergunta=MSG_PERGUNTA_PARCELAS)

        data_pagamento, hora_pagamento = self._resolve_data_hora(data, local)

        try:
            pagamento = Pagamento(
                metodo_pagamento=metodo,
                data=data_pagamento,
                hora=hora_pagamento,
                quant_parcelas=quant_parcelas,
                valor_compra=data.get("valor_compra"),
                moeda=self._resolve_moeda(data.get("moeda")),
                categoria=data.get("categoria"),
                descricao=self._resolve_descricao(data.get("descricao"), texto),
                texto_original=texto,
            )
        except ValidationError:
            return ResultadoExtracao(erro=MSG_INVALID_RESPONSE)

        return ResultadoExtracao(pagamento=pagamento)

    @staticmethod
    def _precisa_perguntar_parcelas(metodo: MetodoPagamento, quant_parcelas: Any) -> bool:
        """True quando a compra é parcelada mas a quantidade de parcelas não foi informada.

        Crédito "à vista" com parcelas informadas é convertido em parcelado pelo próprio
        `Pagamento` (T10), então aqui só falta perguntar quando o número está ausente.
        """
        return quant_parcelas is None and metodo is MetodoPagamento.CREDITO_PARCELADO

    @staticmethod
    def _parse_data(value: Any) -> date | None:
        """Data ISO devolvida pelo LLM, ou `None` se ausente/inválida."""
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip())
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_hora(value: Any) -> time | None:
        """Hora `HH:MM` devolvida pelo LLM, ou `None` se ausente/inválida."""
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not _TIME_RE.match(text):
            return None
        horas, minutos = text.split(":")
        try:
            return time(int(horas), int(minutos))
        except ValueError:
            return None

    def _resolve_data_hora(self, data: dict[str, Any], local: datetime) -> tuple[date, time | None]:
        """Resolve data/hora determinísticas a partir do que o LLM devolveu (passo 9)."""
        data_llm = self._parse_data(data.get("data"))
        data_final = data_llm if data_llm is not None else local.date()

        hora = self._parse_hora(data.get("hora"))
        if hora is not None:
            hora_final: time | None = hora
        elif data_llm is not None and data_llm != local.date():
            # O LLM indicou uma data (passada) sem hora: não inventamos a hora de agora.
            hora_final = None
        else:
            hora_final = local.time().replace(second=0, microsecond=0)
        return data_final, hora_final

    @staticmethod
    def _resolve_descricao(value: Any, texto: str) -> str:
        """Descrição do LLM ou, se ausente/vazia, o próprio texto (limitado a 80 chars)."""
        if isinstance(value, str) and value.strip():
            return value
        return texto.strip()[:80]

    def _resolve_moeda(self, value: Any) -> Any:
        """Usa a moeda devolvida pelo LLM ou a padrão quando ausente (passo 11)."""
        return self.default_currency if value is None else value
