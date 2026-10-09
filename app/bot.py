"""Orquestração do fluxo do bot (v2): mensagem → (STT) → roteador (Jev) →
escrita (extração → confirmação → planilha) | leitura (consulta) | outro.

Spec: specs/tasks/T16-bot-flow-v2.md
"""

import html
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.messages import MSG_SAVED_HEADER
from app.payment import MetodoPagamento, Pagamento
from app.queries import format_valor

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


def _format_pagamento(pagamento: Pagamento) -> str:
    """Linha de forma de pagamento, detalhando parcelas quando aplicável."""
    label = METODO_LABEL[pagamento.metodo_pagamento]
    n = pagamento.quant_parcelas
    if pagamento.metodo_pagamento is MetodoPagamento.CREDITO_PARCELADO and n >= 2:
        parcela = format_valor(pagamento.moeda, pagamento.valor_parcela)
        primeira = pagamento.valor_primeira_parcela
        if primeira != pagamento.valor_parcela:
            primeira_txt = format_valor(pagamento.moeda, primeira)
            return f"{label} em {n}x (1ª de {primeira_txt} + {n - 1}x de {parcela})"
        return f"{label} em {n}x de {parcela}"
    return label


def _format_data(pagamento: Pagamento) -> str:
    """Data (`dd/mm/aaaa`) com hora (`HH:MM`) quando informada."""
    texto = pagamento.data.strftime("%d/%m/%Y")
    if pagamento.hora is not None:
        texto += pagamento.hora.strftime(" %H:%M")
    return texto


def format_confirmacao(pagamento: Pagamento) -> str:
    """Mensagem (HTML) pedindo confirmação do pagamento. Ver spec T16."""
    linhas = [
        "📝 <b>Confirme o pagamento:</b>",
        f"• Valor: {format_valor(pagamento.moeda, pagamento.valor_compra)}",
        f"• Pagamento: {_format_pagamento(pagamento)}",
        f"• Categoria: {pagamento.categoria.value}",
        f"• Descrição: {html.escape(pagamento.descricao)}",
        f"• Data: {_format_data(pagamento)}",
    ]
    return "\n".join(linhas)


def format_registrado(pagamento: Pagamento) -> str:
    """Mensagem (HTML) após gravar o pagamento. Ver spec T16."""
    linhas = format_confirmacao(pagamento).split("\n")
    return "\n".join([MSG_SAVED_HEADER, *linhas[1:]])


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
