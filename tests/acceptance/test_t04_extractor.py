import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domain import Category, Currency, PaymentMethod
from app.extractor import (
    MSG_DEFAULT_NOT_EXPENSE,
    MSG_INVALID_RESPONSE,
    ExpenseExtractor,
    ExtractionError,
)

pytestmark = pytest.mark.task("T04")

TODAY = date(2026, 10, 8)
TEXT = "gastei 35 reais no almoço, paguei em dinheiro"


class FakeCompletions:
    def __init__(self, content=None, exc=None):
        self.content = content
        self.exc = exc
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_extractor(content=None, exc=None, **kwargs):
    completions = FakeCompletions(content, exc)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return ExpenseExtractor(api_key="k", client=client, **kwargs), completions


def payload(**overrides):
    data = {
        "is_expense": True,
        "amount": 35,
        "currency": "BRL",
        "category": "alimentação",
        "description": "almoço",
        "payment_method": "dinheiro",
        "date": None,
        "reason": None,
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


async def test_extracts_expense():
    extractor, _ = make_extractor(payload())
    result = await extractor.extract(TEXT, today=TODAY)
    assert result.error is None
    e = result.expense
    assert e.amount == Decimal("35.00")
    assert e.currency == Currency.BRL
    assert e.category == Category.ALIMENTACAO
    assert e.description == "almoço"
    assert e.payment_method == PaymentMethod.DINHEIRO
    assert e.spent_at == TODAY
    assert e.raw_text == TEXT


async def test_request_parameters():
    extractor, completions = make_extractor(payload())
    await extractor.extract(TEXT, today=TODAY)
    call = completions.calls[0]
    assert call["model"] == "deepseek-flash"
    assert call["temperature"] == 0
    assert call["response_format"] == {"type": "json_object"}
    messages = call["messages"]
    assert messages[0]["role"] == "system"
    assert "JSON" in messages[0]["content"]
    assert "2026-10-08" in messages[0]["content"]
    assert extractor.default_currency in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": TEXT}


async def test_explicit_date_is_used():
    extractor, _ = make_extractor(payload(date="2026-10-07"))
    result = await extractor.extract(TEXT, today=TODAY)
    assert result.expense.spent_at == date(2026, 10, 7)


async def test_invalid_date_falls_back_to_today():
    extractor, _ = make_extractor(payload(date="ontem"))
    result = await extractor.extract(TEXT, today=TODAY)
    assert result.expense.spent_at == TODAY


async def test_missing_currency_uses_default():
    extractor, _ = make_extractor(payload(currency=None), default_currency="BRL")
    result = await extractor.extract(TEXT, today=TODAY)
    assert result.expense.currency == Currency.BRL


async def test_not_an_expense_returns_reason():
    extractor, _ = make_extractor(
        payload(is_expense=False, amount=None, reason="Isso é uma saudação.")
    )
    result = await extractor.extract("oi, tudo bem?", today=TODAY)
    assert result.expense is None
    assert result.error == "Isso é uma saudação."


async def test_not_an_expense_without_reason_uses_default():
    extractor, _ = make_extractor(payload(is_expense=False, amount=None, reason=None))
    result = await extractor.extract("oi", today=TODAY)
    assert result.expense is None
    assert result.error == MSG_DEFAULT_NOT_EXPENSE


@pytest.mark.parametrize("content", ["isso não é json", "", None, "[]"])
async def test_invalid_json_returns_error(content):
    extractor, _ = make_extractor(content)
    result = await extractor.extract(TEXT, today=TODAY)
    assert result.expense is None
    assert result.error == MSG_INVALID_RESPONSE


async def test_invalid_amount_returns_error():
    extractor, _ = make_extractor(payload(amount=None))
    result = await extractor.extract(TEXT, today=TODAY)
    assert result.expense is None
    assert result.error == MSG_INVALID_RESPONSE


async def test_code_fenced_json_is_accepted():
    extractor, _ = make_extractor("```json\n" + payload() + "\n```")
    result = await extractor.extract(TEXT, today=TODAY)
    assert result.expense is not None


async def test_empty_text_does_not_call_api():
    extractor, completions = make_extractor(payload())
    result = await extractor.extract("   ", today=TODAY)
    assert result.expense is None
    assert result.error == MSG_DEFAULT_NOT_EXPENSE
    assert completions.calls == []


async def test_api_exception_raises_extraction_error():
    extractor, _ = make_extractor(exc=RuntimeError("401 unauthorized"))
    with pytest.raises(ExtractionError):
        await extractor.extract(TEXT, today=TODAY)


def test_default_client_is_async_openai():
    from openai import AsyncOpenAI

    extractor = ExpenseExtractor(api_key="k")
    assert isinstance(extractor.client, AsyncOpenAI)
    assert "api.deepseek.com" in str(extractor.client.base_url)
