"""Modelo de domínio do gasto e formatações.

Spec: specs/tasks/T01-domain-model.md
"""

import html
import unicodedata
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel, field_validator


class Currency(StrEnum):
    BRL = "BRL"
    USD = "USD"
    EUR = "EUR"


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
    PIX = "pix"
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
    if not isinstance(value, str):
        raise ValueError("descrição deve ser um texto")
    text = value.strip()
    if not text or len(text) > _DESCRIPTION_MAX_LENGTH:
        raise ValueError("descrição deve ter entre 1 e 200 caracteres")
    return text


def _strip_accents(text: str) -> str:
    """Remove acentos (marcas diacríticas) de um texto."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _normalize_key(value: object) -> str:
    """Chave de comparação: minúsculas, sem acentos e sem espaços."""
    text = _strip_accents(str(value).strip().lower())
    return "".join(text.split())


_CURRENCY_ALIASES: dict[str, Currency] = {
    "brl": Currency.BRL,
    "r$": Currency.BRL,
    "real": Currency.BRL,
    "reais": Currency.BRL,
    "usd": Currency.USD,
    "us$": Currency.USD,
    "$": Currency.USD,
    "dolar": Currency.USD,
    "dolares": Currency.USD,
    "eur": Currency.EUR,
    "€": Currency.EUR,
    "euro": Currency.EUR,
    "euros": Currency.EUR,
}

_CATEGORY_BY_KEY: dict[str, Category] = {_normalize_key(c.value): c for c in Category}
_PAYMENT_METHOD_BY_KEY: dict[str, PaymentMethod] = {
    _normalize_key(p.value): p for p in PaymentMethod
}


def _normalize_currency(value: object) -> Currency:
    """Normaliza a moeda por aliases; `None` vira BRL e desconhecida é inválida."""
    if value is None:
        return Currency.BRL
    try:
        return _CURRENCY_ALIASES[_normalize_key(value)]
    except KeyError as exc:
        raise ValueError(f"moeda inválida: {value!r}") from exc


def _normalize_category(value: object) -> Category:
    """Normaliza a categoria; desconhecida ou `None` vira `outros`."""
    if value is None:
        return Category.OUTROS
    return _CATEGORY_BY_KEY.get(_normalize_key(value), Category.OUTROS)


def _normalize_payment_method(value: object) -> PaymentMethod:
    """Normaliza o pagamento; desconhecido ou `None` vira `outro`."""
    if value is None:
        return PaymentMethod.OUTRO
    return _PAYMENT_METHOD_BY_KEY.get(_normalize_key(value), PaymentMethod.OUTRO)


class Expense(BaseModel):
    """Um gasto. As regras de validação/normalização estão na spec T01."""

    amount: Decimal
    currency: Currency = Currency.BRL
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

    @field_validator("currency", mode="before")
    @classmethod
    def _validate_currency(cls, value: object) -> Currency:
        return _normalize_currency(value)

    @field_validator("category", mode="before")
    @classmethod
    def _validate_category(cls, value: object) -> Category:
        return _normalize_category(value)

    @field_validator("payment_method", mode="before")
    @classmethod
    def _validate_payment_method(cls, value: object) -> PaymentMethod:
        return _normalize_payment_method(value)


def format_confirmation(expense: Expense) -> str:
    """Mensagem (HTML do Telegram) pedindo confirmação do gasto. Ver spec T01."""
    return (
        "📝 <b>Confirme o gasto:</b>\n"
        f"• Valor: {expense.amount:.2f} {expense.currency.value}\n"
        f"• Categoria: {expense.category.value}\n"
        f"• Descrição: {html.escape(expense.description)}\n"
        f"• Pagamento: {expense.payment_method.value}\n"
        f"• Data: {expense.spent_at.strftime('%d/%m/%Y')}"
    )


def to_sheet_row(expense: Expense, user: str, recorded_at: datetime) -> list[str | float]:
    """Linha a ser inserida na planilha, na ordem de SHEET_HEADER. Ver spec T01."""
    return [
        expense.spent_at.isoformat(),
        expense.description,
        expense.category.value,
        float(expense.amount),
        expense.currency.value,
        expense.payment_method.value,
        user,
        recorded_at.isoformat(),
        expense.raw_text,
    ]
