"""Testes unitários do ExpenseExtractor (T04, subtarefas 1 e 2)."""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from app.extractor import (
    MSG_DEFAULT_NOT_EXPENSE,
    MSG_INVALID_RESPONSE,
    ExpenseExtractor,
    ExtractionError,
)

TODAY = date(2026, 10, 8)
TEXT = "gastei 35 kuai no almoço"


class _Completions:
    def __init__(self, exc: Exception | None = None, content: object = "{}") -> None:
        self.exc = exc
        self.content = content
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _make(**kwargs):
    completions = _Completions(kwargs.pop("exc", None), content=kwargs.pop("content", "{}"))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return ExpenseExtractor(api_key="k", client=client, **kwargs), completions


def test_init_stores_attributes_and_injected_client():
    extractor, _ = _make(model="m", base_url="https://x", default_currency="BRL")
    assert extractor.model == "m"
    assert extractor.base_url == "https://x"
    assert extractor.default_currency == "BRL"
    assert extractor.client is not None


def test_build_messages_formats_prompt_and_user_text():
    extractor, _ = _make(default_currency="BRL")
    system, user = extractor._build_messages(TEXT, TODAY)
    assert system["role"] == "system"
    assert "2026-10-08" in system["content"]
    assert "BRL" in system["content"]
    assert user == {"role": "user", "content": TEXT}


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
async def test_blank_text_returns_default_error_without_calling_api(text):
    extractor, completions = _make()
    result = await extractor.extract(text, today=TODAY)
    assert result.expense is None
    assert result.error == MSG_DEFAULT_NOT_EXPENSE
    assert completions.calls == []


async def test_api_exception_is_chained_into_extraction_error():
    extractor, _ = _make(exc=RuntimeError("boom"))
    with pytest.raises(ExtractionError) as info:
        await extractor.extract(TEXT, today=TODAY)
    assert isinstance(info.value.__cause__, RuntimeError)


@pytest.mark.parametrize("content", ["isso não é json", "", None, "[]", "42", "null"])
async def test_invalid_json_content_returns_invalid_response(content):
    extractor, _ = _make(content=content)
    result = await extractor.extract(TEXT, today=TODAY)
    assert result.expense is None
    assert result.error == MSG_INVALID_RESPONSE


async def test_code_fenced_json_is_parsed():
    content = "```json\n" + json.dumps({"is_expense": False, "reason": "saudação"}) + "\n```"
    extractor, _ = _make(content=content)
    result = await extractor.extract(TEXT, today=TODAY)
    assert result.expense is None
    assert result.error == "saudação"


async def test_plain_fenced_json_is_parsed():
    content = "```\n" + json.dumps({"is_expense": False, "reason": "oi"}) + "\n```"
    extractor, _ = _make(content=content)
    result = await extractor.extract(TEXT, today=TODAY)
    assert result.error == "oi"


async def test_not_expense_uses_returned_reason():
    content = json.dumps({"is_expense": False, "reason": "Isso é uma saudação."})
    extractor, _ = _make(content=content)
    result = await extractor.extract(TEXT, today=TODAY)
    assert result.expense is None
    assert result.error == "Isso é uma saudação."


async def test_not_expense_without_reason_uses_default():
    extractor, _ = _make(content=json.dumps({"is_expense": False, "reason": None}))
    result = await extractor.extract(TEXT, today=TODAY)
    assert result.expense is None
    assert result.error == MSG_DEFAULT_NOT_EXPENSE
