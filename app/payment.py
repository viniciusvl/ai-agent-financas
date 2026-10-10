"""Modelo de pagamento (v2) e cálculo determinístico de parcelas.

O LLM nunca calcula valores de parcela: a aplicação calcula a partir de valor_compra e
quant_parcelas. Spec: specs/tasks/T10-payment-model.md
"""

import re
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
    BOLETO = "boleto"
    TRANSFERENCIA = "transferencia"
    OUTRO = "outro"


MAX_PARCELAS = 24

_CENTAVOS = Decimal("0.01")

# Aliases de método de pagamento. As chaves passam por `_chave_metodo` (minúsculas, sem acento
# e com espaços/hífens/underscores removidos), então variantes como "boleto bancário" e
# "boleto-bancario" caem na mesma chave.
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
    "boleto": MetodoPagamento.BOLETO,
    "boletobancario": MetodoPagamento.BOLETO,
    "transferencia": MetodoPagamento.TRANSFERENCIA,
    "transferenciabancaria": MetodoPagamento.TRANSFERENCIA,
    "ted": MetodoPagamento.TRANSFERENCIA,
    "doc": MetodoPagamento.TRANSFERENCIA,
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


# Primeiro número (inteiro ou decimal, com `.`/`,` como separador) presente numa string.
_NUMERO_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _parse_quant_parcelas(value: object) -> int:
    """Converte a quantidade de parcelas para `int`.

    O LLM pode devolver o número como texto (`"10"`, `" 6 "`, `"10x"`) ou como float/Decimal
    integral (`10.0`). `None` vira 1. Rejeita `bool`, valores não-integrais (`3.5`) e texto sem
    número.
    """
    if value is None:
        return 1
    if isinstance(value, bool):
        raise ValueError(f"quantidade de parcelas inválida: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, (float, Decimal)):
        try:
            inteiro = int(value)
        except (ValueError, OverflowError, TypeError) as exc:
            raise ValueError(f"quantidade de parcelas inválida: {value!r}") from exc
        if value != inteiro:
            raise ValueError(f"quantidade de parcelas inválida: {value!r}")
        return inteiro
    if isinstance(value, str):
        match = _NUMERO_RE.search(value)
        if match is None:
            raise ValueError(f"quantidade de parcelas inválida: {value!r}")
        numero = Decimal(match.group().replace(",", "."))
        if numero != numero.to_integral_value():
            raise ValueError(f"quantidade de parcelas inválida: {value!r}")
        return int(numero)
    raise ValueError(f"quantidade de parcelas inválida: {value!r}")


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
    moeda: Currency = Currency.BRL
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
        return _parse_quant_parcelas(value)

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
