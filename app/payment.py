"""Modelo de pagamento (v2) e cálculo determinístico de parcelas.

O LLM nunca calcula valores de parcela: a aplicação calcula a partir de valor_compra e
quant_parcelas. Spec: specs/tasks/T10-payment-model.md
"""

from datetime import date, time
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.domain import (
    Category,
    Currency,
    _normalize_category,
    _normalize_currency,
    _normalize_description,
    _parse_amount,
    _strip_accents,
)


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

# Aliases de método de pagamento. As chaves passam por `_chave_metodo` (minúsculas, sem acento
# e com espaços/hífens/underscores removidos), então variantes como "wechat pay", "wechat_pay"
# e "WeChat" caem na mesma chave.
_METODO_POR_CHAVE: dict[str, MetodoPagamento] = {
    "dinheiro": MetodoPagamento.DINHEIRO,
    "cash": MetodoPagamento.DINHEIRO,
    "especie": MetodoPagamento.DINHEIRO,
    "debito": MetodoPagamento.DEBITO,
    "cartaodedebito": MetodoPagamento.DEBITO,
    "credito": MetodoPagamento.CREDITO_A_VISTA,
    "cartao": MetodoPagamento.CREDITO_A_VISTA,
    "cartaodecredito": MetodoPagamento.CREDITO_A_VISTA,
    "creditoavista": MetodoPagamento.CREDITO_A_VISTA,
    "parcelado": MetodoPagamento.CREDITO_PARCELADO,
    "creditoparcelado": MetodoPagamento.CREDITO_PARCELADO,
    "pix": MetodoPagamento.PIX,
    "alipay": MetodoPagamento.ALIPAY,
    "zhifubao": MetodoPagamento.ALIPAY,
    "wechat": MetodoPagamento.WECHAT_PAY,
    "wechatpay": MetodoPagamento.WECHAT_PAY,
    "weixin": MetodoPagamento.WECHAT_PAY,
}


def _chave_metodo(value: object) -> str:
    """Chave de comparação: minúsculas, sem acentos e sem espaços/hífens/underscores."""
    texto = _strip_accents(str(value).strip().lower())
    return "".join(ch for ch in texto if ch not in " -_")


def normalizar_metodo(value: object) -> MetodoPagamento:
    """Normaliza o método de pagamento; desconhecido ou `None` vira `outro`."""
    if value is None:
        return MetodoPagamento.OUTRO
    return _METODO_POR_CHAVE.get(_chave_metodo(value), MetodoPagamento.OUTRO)


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

    @field_validator("metodo_pagamento", mode="before")
    @classmethod
    def _validar_metodo_pagamento(cls, value: object) -> MetodoPagamento:
        return normalizar_metodo(value)

    @field_validator("valor_compra", mode="before")
    @classmethod
    def _validar_valor_compra(cls, value: object) -> Decimal:
        return _parse_amount(value)

    @field_validator("descricao", mode="before")
    @classmethod
    def _validar_descricao(cls, value: object) -> str:
        return _normalize_description(value)

    @field_validator("moeda", mode="before")
    @classmethod
    def _validar_moeda(cls, value: object) -> Currency:
        return _normalize_currency(value)

    @field_validator("categoria", mode="before")
    @classmethod
    def _validar_categoria(cls, value: object) -> Category:
        return _normalize_category(value)

    @field_validator("quant_parcelas", mode="before")
    @classmethod
    def _validar_quant_parcelas(cls, value: object) -> int:
        if value is None:
            return 1
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"quantidade de parcelas inválida: {value!r}")
        return value

    @model_validator(mode="after")
    def _aplicar_regras_de_parcelas(self) -> "Pagamento":
        """Aplica as regras de parcelas da spec T10 (após a validação dos campos)."""
        if self.metodo_pagamento is MetodoPagamento.CREDITO_A_VISTA:
            if self.quant_parcelas >= 2:
                self.metodo_pagamento = MetodoPagamento.CREDITO_PARCELADO
            else:
                self.quant_parcelas = 1

        if self.metodo_pagamento is MetodoPagamento.CREDITO_PARCELADO:
            if not 2 <= self.quant_parcelas <= MAX_PARCELAS:
                raise ValueError(f"credito_parcelado exige entre 2 e {MAX_PARCELAS} parcelas")
        else:
            self.quant_parcelas = 1
        return self

    @property
    def parcelas(self) -> list[Decimal]:
        """Parcelas calculadas pela aplicação (o LLM nunca as define)."""
        return calcular_parcelas(self.valor_compra, self.quant_parcelas)

    @property
    def valor_parcela(self) -> Decimal:
        """Valor da última parcela (a base, sem a diferença de arredondamento)."""
        return self.parcelas[-1]

    @property
    def valor_primeira_parcela(self) -> Decimal:
        """Valor da primeira parcela (absorve a diferença de arredondamento)."""
        return self.parcelas[0]
