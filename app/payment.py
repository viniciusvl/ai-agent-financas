"""Modelo de pagamento (v2) e cálculo determinístico de parcelas.

O LLM nunca calcula valores de parcela: a aplicação calcula a partir de valor_compra e
quant_parcelas. Spec: specs/tasks/T10-payment-model.md
"""

from datetime import date, time
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.domain import Category, Currency


class MetodoPagamento(StrEnum):
    DINHEIRO = "dinheiro"
    DEBITO = "debito"
    CREDITO_A_VISTA = "credito_a_vista"
    CREDITO_PARCELADO = "credito_parcelado"
    PIX = "pix"
    ALIPAY = "alipay"
    WECHAT_PAY = "wechat_pay"
    OUTRO = "outro"


MAX_PARCELAS = 24

_CENTAVOS = Decimal("0.01")


def calcular_parcelas(valor_compra: Decimal, quant_parcelas: int) -> list[Decimal]:
    """Divide o valor em parcelas que somam exatamente o total. Ver spec T10.

    A parcela base é `valor_compra / n` arredondada para baixo em centavos; a diferença
    (para fechar o total exato) vai para a primeira parcela.
    """
    if isinstance(quant_parcelas, bool) or not isinstance(quant_parcelas, int):
        raise ValueError(f"quantidade de parcelas inválida: {quant_parcelas!r}")
    if not 1 <= quant_parcelas <= MAX_PARCELAS:
        raise ValueError(f"quantidade de parcelas deve estar entre 1 e {MAX_PARCELAS}")

    valor = valor_compra if isinstance(valor_compra, Decimal) else Decimal(str(valor_compra))
    if valor <= 0:
        raise ValueError("valor da compra deve ser maior que zero")

    base = (valor / quant_parcelas).quantize(_CENTAVOS, rounding=ROUND_DOWN)
    diferenca = valor - base * quant_parcelas
    primeira = base + diferenca
    return [primeira] + [base] * (quant_parcelas - 1)


class Pagamento(BaseModel):
    """Pagamento a registrar. Campos de entrada desconhecidos (ex.: valor_parcela) são ignorados."""

    model_config = ConfigDict(extra="ignore")

    metodo_pagamento: MetodoPagamento = MetodoPagamento.OUTRO
    data: date
    hora: time | None = None
    quant_parcelas: int = 1
    valor_compra: Decimal
    moeda: Currency = Currency.CNY
    categoria: Category = Category.OUTROS
    descricao: str
    texto_original: str = ""

    # TODO(T10): validators e regras de parcelas.

    @property
    def parcelas(self) -> list[Decimal]:
        raise NotImplementedError("T10")

    @property
    def valor_parcela(self) -> Decimal:
        raise NotImplementedError("T10")

    @property
    def valor_primeira_parcela(self) -> Decimal:
        raise NotImplementedError("T10")
