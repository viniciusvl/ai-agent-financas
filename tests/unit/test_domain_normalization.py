"""Testes unitários da subtarefa 2 de T01 (currency, category e payment_method)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain import Category, Currency, Expense, PaymentMethod


def make(**overrides):
    data = dict(
        amount=Decimal("1.00"),
        description="teste",
        spent_at=date(2026, 10, 8),
    )
    data.update(overrides)
    return Expense(**data)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BRL", Currency.BRL),
        ("  brl  ", Currency.BRL),
        ("R$", Currency.BRL),
        ("REAL", Currency.BRL),
        ("Reais", Currency.BRL),
        (None, Currency.BRL),
        (Currency.USD, Currency.USD),
        ("US$", Currency.USD),
        ("$", Currency.USD),
        ("dólares", Currency.USD),
        ("EUR", Currency.EUR),
        ("€", Currency.EUR),
        ("Euro", Currency.EUR),
        ("euros", Currency.EUR),
    ],
)
def test_currency_aliases(raw, expected):
    assert make(currency=raw).currency == expected


@pytest.mark.parametrize("raw", ["gbp", "peso", "chf", 42, ""])
def test_currency_invalid(raw):
    with pytest.raises(ValidationError):
        make(currency=raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hospedagem", Category.HOSPEDAGEM),
        ("PASSEIOS", Category.PASSEIOS),
        ("compras", Category.COMPRAS),
        ("compras ", Category.COMPRAS),
        ("descrição qualquer", Category.OUTROS),
        (Category.TRANSPORTE, Category.TRANSPORTE),
        (None, Category.OUTROS),
    ],
)
def test_category_normalization(raw, expected):
    assert make(category=raw).category == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("DINHEIRO", PaymentMethod.DINHEIRO),
        ("Cartao", PaymentMethod.CARTAO),
        ("paypal", PaymentMethod.OUTRO),
        ("outro", PaymentMethod.OUTRO),
        ("pix", PaymentMethod.PIX),
        (PaymentMethod.CARTAO, PaymentMethod.CARTAO),
        (None, PaymentMethod.OUTRO),
    ],
)
def test_payment_method_normalization(raw, expected):
    assert make(payment_method=raw).payment_method == expected
