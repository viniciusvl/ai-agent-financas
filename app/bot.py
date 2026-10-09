"""Orquestração do fluxo do bot (v2): mensagem → (STT) → roteador (Jev) →
escrita (extração → confirmação → planilha) | leitura (consulta) | outro.

Spec: specs/tasks/T16-bot-flow-v2.md
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.payment import MetodoPagamento, Pagamento

METODO_LABEL: dict[MetodoPagamento, str] = {
    MetodoPagamento.DINHEIRO: "dinheiro",
    MetodoPagamento.DEBITO: "débito",
    MetodoPagamento.CREDITO_A_VISTA: "crédito à vista",
    MetodoPagamento.CREDITO_PARCELADO: "crédito parcelado",
    MetodoPagamento.PIX: "Pix",
    MetodoPagamento.ALIPAY: "Alipay",
    MetodoPagamento.WECHAT_PAY: "WeChat Pay",
    MetodoPagamento.OUTRO: "outro",
}


def format_confirmacao(pagamento: Pagamento) -> str:
    """Mensagem (HTML) pedindo confirmação do pagamento. Ver spec T16."""
    raise NotImplementedError("T16")


def format_registrado(pagamento: Pagamento) -> str:
    """Mensagem (HTML) após gravar o pagamento. Ver spec T16."""
    raise NotImplementedError("T16")


class BotService:
    def __init__(
        self,
        telegram: Any,
        transcriber: Any,
        router: Any,
        extractor: Any,
        read_agent: Any,
        store: Any,
        writer: Any,
        allowed_user_ids: set[int],
        timezone: str = "Asia/Shanghai",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        raise NotImplementedError("T16")

    async def handle_update(self, update: dict[str, Any]) -> None:
        """Processa um Update do Telegram. Nunca propaga exceções."""
        raise NotImplementedError("T16")
