"""Testes unitários do ExpenseExtractor (T04, subtarefa 1)."""

from datetime import date
from types import SimpleNamespace

import pytest

from app.extractor import MSG_DEFAULT_NOT_EXPENSE, ExpenseExtractor, ExtractionError

TODAY = date(2026, 10, 8)
TEXT = "gastei 35 kuai no almoço"


class _Completions:
    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        message = SimpleNamespace(content="{}")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _make(**kwargs):
    completions = _Completions(kwargs.pop("exc", None))
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
