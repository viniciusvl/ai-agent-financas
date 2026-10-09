"""Testes unitários da subtarefa 3 de T01 (format_confirmation e to_sheet_row)."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain import (
    SHEET_HEADER,
    Category,
    Currency,
    Expense,
    PaymentMethod,
    format_confirmation,
    to_sheet_row,
)


def make(**overrides):
    data = dict(
        amount=Decimal("35.5"),
        currency=Currency.CNY,
        category=Category.ALIMENTACAO,
        description="almoço",
        payment_method=PaymentMethod.ALIPAY,
        spent_at=date(2026, 10, 8),
        raw_text="gastei 35,5 no almoço",
    )
    data.update(overrides)
    return Expense(**data)


def test_format_confirmation_exact():
    assert format_confirmation(make()) == (
        "📝 <b>Confirme o gasto:</b>\n"
        "• Valor: 35.50 CNY\n"
        "• Categoria: alimentação\n"
        "• Descrição: almoço\n"
        "• Pagamento: alipay\n"
        "• Data: 08/10/2026"
    )


def test_format_confirmation_escapes_html():
    text = format_confirmation(make(description="<b>x</b> & y"))
    assert "• Descrição: &lt;b&gt;x&lt;/b&gt; &amp; y" in text


def test_format_confirmation_uses_normalized_values():
    text = format_confirmation(
        make(amount="1.234,56", currency="us$", category="transporte", payment_method="cartao")
    )
    assert "• Valor: 1234.56 USD" in text
    assert "• Categoria: transporte" in text
    assert "• Pagamento: cartão" in text


def test_format_confirmation_zero_pads_amount():
    assert "• Valor: 5.00 CNY" in format_confirmation(make(amount=5))


def test_to_sheet_row_order_and_values():
    recorded_at = datetime(2026, 10, 8, 12, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    row = to_sheet_row(make(), user="Vini", recorded_at=recorded_at)
    assert row == [
        "2026-10-08",
        "almoço",
        "alimentação",
        35.5,
        "CNY",
        "alipay",
        "Vini",
        "2026-10-08T12:30:00+08:00",
        "gastei 35,5 no almoço",
    ]
    assert isinstance(row[3], float)
    assert len(row) == len(SHEET_HEADER)


def test_to_sheet_row_contains_raw_text_verbatim():
    raw = "  linha\ncom quebra  "
    row = to_sheet_row(
        make(raw_text=raw),
        user="Vini",
        recorded_at=datetime(2026, 10, 8, 12, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    assert row[-1] == raw
