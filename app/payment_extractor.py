"""Extração de pagamentos (intenção "escrita", v2) com DeepSeek.

O LLM extrai os campos; data/hora padrão vêm do timestamp da mensagem e o valor das parcelas é
calculado pela aplicação (app/payment.py). Spec: specs/tasks/T13-payment-extractor.md
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.extractor import MSG_DEFAULT_NOT_EXPENSE, MSG_INVALID_RESPONSE, ExtractionError
from app.payment import Pagamento
from app.sheet_schema import SheetSchema

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
        raise NotImplementedError("T13")

    async def extract(self, texto: str, recebido_em: datetime) -> ResultadoExtracao:
        raise NotImplementedError("T13")
