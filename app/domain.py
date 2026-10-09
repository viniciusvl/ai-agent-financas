"""Modelo de domínio do gasto e formatações.

Spec: specs/tasks/T01-domain-model.md
"""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel, field_validator


class Currency(StrEnum):
    CNY = "CNY"
    BRL = "BRL"
    USD = "USD"


class Category(StrEnum):
    ALIMENTACAO = "alimentação"
    TRANSPORTE = "transporte"
    HOSPEDAGEM = "hospedagem"
    COMPRAS = "compras"
    PASSEIOS = "passeios"
    OUTROS = "outros"


class PaymentMethod(StrEnum):
    DINHEIRO = "dinheiro"
    CARTAO = "cartão"
    ALIPAY = "alipay"
    WECHAT = "wechat"
    OUTRO = "outro"


SHEET_HEADER: list[str] = [
    "Data",
    "Descrição",
    "Categoria",
    "Valor",
    "Moeda",
    "Pagamento",
    "Usuário",
    "Registrado em",
    "Texto original",
]

_DESCRIPTION_MAX_LENGTH = 200
_AMOUNT_QUANTUM = Decimal("0.01")


def _parse_amount(value: object) -> Decimal:
    """Normaliza o valor monetário para Decimal com 2 casas (ROUND_HALF_UP)."""
    if isinstance(value, bool):  # bool é subclasse de int; não é um valor válido
        raise ValueError("valor inválido")

    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, float):
        amount = Decimal(str(value))
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("valor não pode ser vazio")
        if "," in text:
            # Formato pt-BR: "." separa milhar e "," separa decimal.
            text = text.replace(".", "").replace(",", ".")
        try:
            amount = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(f"valor inválido: {value!r}") from exc
    else:
        raise ValueError(f"valor inválido: {value!r}")

    if not amount.is_finite():
        raise ValueError(f"valor inválido: {value!r}")

    amount = amount.quantize(_AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise ValueError("valor deve ser maior que zero")
    return amount


def _normalize_description(value: object) -> str:
    """Remove espaços e valida o tamanho da descrição (1–200 caracteres)."""
    text = str(value).strip()
    if not text or len(text) > _DESCRIPTION_MAX_LENGTH:
        raise ValueError("descrição deve ter entre 1 e 200 caracteres")
    return text


class Expense(BaseModel):
    """Um gasto. As regras de validação/normalização estão na spec T01."""

    amount: Decimal
    currency: Currency = Currency.CNY
    category: Category = Category.OUTROS
    description: str
    payment_method: PaymentMethod = PaymentMethod.OUTRO
    spent_at: date
    raw_text: str = ""

    @field_validator("amount", mode="before")
    @classmethod
    def _validate_amount(cls, value: object) -> Decimal:
        return _parse_amount(value)

    @field_validator("description", mode="before")
    @classmethod
    def _validate_description(cls, value: object) -> str:
        return _normalize_description(value)


def format_confirmation(expense: Expense) -> str:
    """Mensagem (HTML do Telegram) pedindo confirmação do gasto. Ver spec T01."""
    raise NotImplementedError("T01")


def to_sheet_row(expense: Expense, user: str, recorded_at: datetime) -> list[str | float]:
    """Linha a ser inserida na planilha, na ordem de SHEET_HEADER. Ver spec T01."""
    raise NotImplementedError("T01")
