"""Testes unitários da subtarefa 1 de T01 (amount e description)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain import Expense


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
        ("0.005", Decimal("0.01")),  # ROUND_HALF_UP
        ("1.005", Decimal("1.01")),
        ("1.234", Decimal("1.23")),
        ("1.235", Decimal("1.24")),
        ("1.000,10", Decimal("1000.10")),
        (Decimal("0.1"), Decimal("0.10")),
    ],
)
def test_amount_rounding(raw, expected):
    assert make(amount=raw).amount == expected


@pytest.mark.parametrize("raw", [0, -5, "-1,00", "  ", "  ,  ", None, [1]])
def test_amount_invalid(raw):
    with pytest.raises(ValidationError):
        make(amount=raw)


def test_description_limit_boundary():
    assert make(description="x" * 200).description == "x" * 200


@pytest.mark.parametrize("raw", [None, 123, 12.5, ["x"], Decimal("1")])
def test_description_on_non_string(raw):
    with pytest.raises(ValidationError):
        make(description=raw)
