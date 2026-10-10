from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.domain import (
    SHEET_HEADER,
    Category,
    Currency,
    Expense,
    PaymentMethod,
    format_confirmation,
    to_sheet_row,
)

pytestmark = pytest.mark.task("T01")


def make(**overrides):
    data = dict(
        amount=Decimal("35.5"),
        currency=Currency.BRL,
        category=Category.ALIMENTACAO,
        description="almoço",
        payment_method=PaymentMethod.DINHEIRO,
        spent_at=date(2026, 10, 8),
        raw_text="gastei 35,5 no almoço",
    )
    data.update(overrides)
    return Expense(**data)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (Decimal("35.5"), Decimal("35.50")),
        ("12.345", Decimal("12.35")),
        ("35,50", Decimal("35.50")),
        (" 1.234,56 ", Decimal("1234.56")),
        (80, Decimal("80.00")),
        (19.99, Decimal("19.99")),
    ],
)
def test_amount_is_normalized_to_two_decimals(raw, expected):
    expense = make(amount=raw)
    assert expense.amount == expected
    assert expense.amount.as_tuple().exponent == -2


@pytest.mark.parametrize("raw", [0, -1, "0,00", "abc", ""])
def test_amount_must_be_positive_number(raw):
    with pytest.raises(ValidationError):
        make(amount=raw)


def test_description_is_stripped():
    assert make(description="  almoço  ").description == "almoço"


@pytest.mark.parametrize("raw", ["", "   ", "x" * 201])
def test_description_invalid(raw):
    with pytest.raises(ValidationError):
        make(description=raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("brl", Currency.BRL),
        ("R$", Currency.BRL),
        ("reais", Currency.BRL),
        ("usd", Currency.USD),
        ("US$", Currency.USD),
        ("dólar", Currency.USD),
        ("dolares", Currency.USD),
    ],
)
def test_currency_aliases(raw, expected):
    assert make(currency=raw).currency == expected


def test_unknown_currency_is_rejected():
    with pytest.raises(ValidationError):
        make(currency="EUR")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Transporte", Category.TRANSPORTE),
        ("alimentacao", Category.ALIMENTACAO),
        ("ALIMENTAÇÃO", Category.ALIMENTACAO),
        ("xyz", Category.OUTROS),
        (None, Category.OUTROS),
    ],
)
def test_category_normalization(raw, expected):
    assert make(category=raw).category == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Dinheiro", PaymentMethod.DINHEIRO),
        ("cartao", PaymentMethod.CARTAO),
        ("pix", PaymentMethod.OUTRO),
        (None, PaymentMethod.OUTRO),
    ],
)
def test_payment_method_normalization(raw, expected):
    assert make(payment_method=raw).payment_method == expected


def test_format_confirmation_exact():
    assert format_confirmation(make()) == (
        "📝 <b>Confirme o gasto:</b>\n"
        "• Valor: 35.50 BRL\n"
        "• Categoria: alimentação\n"
        "• Descrição: almoço\n"
        "• Pagamento: dinheiro\n"
        "• Data: 08/10/2026"
    )


def test_format_confirmation_escapes_html():
    text = format_confirmation(make(description="<b>x</b> & y"))
    assert "• Descrição: &lt;b&gt;x&lt;/b&gt; &amp; y" in text


def test_sheet_header():
    assert SHEET_HEADER == [
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


def test_to_sheet_row():
    recorded_at = datetime(2026, 10, 8, 12, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
    row = to_sheet_row(make(), user="Vini", recorded_at=recorded_at)
    assert row == [
        "2026-10-08",
        "almoço",
        "alimentação",
        35.5,
        "BRL",
        "dinheiro",
        "Vini",
        "2026-10-08T12:30:00-03:00",
        "gastei 35,5 no almoço",
    ]
    assert isinstance(row[3], float)
    assert len(row) == len(SHEET_HEADER)


def test_json_roundtrip():
    expense = make()
    assert Expense.model_validate_json(expense.model_dump_json()) == expense
