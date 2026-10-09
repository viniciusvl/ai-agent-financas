"""Modelo de domínio do gasto e formatações.

Spec: specs/tasks/T01-domain-model.md
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


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


class Expense(BaseModel):
    """Um gasto. As regras de validação/normalização estão na spec T01."""

    amount: Decimal
    currency: Currency = Currency.CNY
    category: Category = Category.OUTROS
    description: str
    payment_method: PaymentMethod = PaymentMethod.OUTRO
    spent_at: date
    raw_text: str = ""

    # TODO(T01): validators de amount, currency, category, payment_method e description.


def format_confirmation(expense: Expense) -> str:
    """Mensagem (HTML do Telegram) pedindo confirmação do gasto. Ver spec T01."""
    raise NotImplementedError("T01")


def to_sheet_row(expense: Expense, user: str, recorded_at: datetime) -> list[str | float]:
    """Linha a ser inserida na planilha, na ordem de SHEET_HEADER. Ver spec T01."""
    raise NotImplementedError("T01")
