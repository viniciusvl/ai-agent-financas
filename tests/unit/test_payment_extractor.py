"""Testes unitários do PaymentExtractor (T13, subtarefa 1: init, mensagens e chamada à API)."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.extractor import MSG_DEFAULT_NOT_EXPENSE, MSG_INVALID_RESPONSE, ExtractionError
from app.payment_extractor import PaymentExtractor
from app.prompts import PAYMENT_EXTRACTION_SYSTEM_PROMPT
from app.sheet_schema import SheetSchema

RECEBIDO = datetime(2026, 10, 8, 22, 30, 41, tzinfo=ZoneInfo("UTC"))
TEXTO = "almoço 35 kuai alipay"


@pytest.fixture
def schema() -> SheetSchema:
    return SheetSchema.from_dict(
        {
            "aba": "Gastos",
            "colunas": [
                {"nome": "Data", "campo": "data", "tipo": "data"},
                {"nome": "Valor", "campo": "valor_compra", "tipo": "moeda"},
            ],
        }
    )


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


def _make(schema: SheetSchema, **kwargs):
    completions = _Completions(kwargs.pop("exc", None), content=kwargs.pop("content", "{}"))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return PaymentExtractor(api_key="k", schema=schema, client=client, **kwargs), completions


def test_init_stores_attributes_and_injected_client(schema):
    extractor, _ = _make(
        schema, model="m", base_url="https://x", default_currency="BRL", timezone="Asia/Tokyo"
    )
    assert extractor.model == "m"
    assert extractor.base_url == "https://x"
    assert extractor.schema is schema
    assert extractor.default_currency == "BRL"
    assert extractor.timezone == "Asia/Tokyo"
    assert extractor.client is not None


def test_default_client_is_async_openai(schema):
    from openai import AsyncOpenAI

    extractor = PaymentExtractor(api_key="k", schema=schema)
    assert isinstance(extractor.client, AsyncOpenAI)
    assert "api.deepseek.com" in str(extractor.client.base_url)


def test_build_messages_formats_prompt_in_message_timezone(schema):
    extractor, _ = _make(schema, default_currency="BRL")
    local = RECEBIDO.astimezone(ZoneInfo("Asia/Shanghai"))
    system, user = extractor._build_messages(TEXTO, local)
    assert system["role"] == "system"
    assert system["content"] == PAYMENT_EXTRACTION_SYSTEM_PROMPT.format(
        agora="06:30",
        hoje="2026-10-09",
        moeda_padrao="BRL",
        schema=schema.prompt_context(),
    )
    assert user == {"role": "user", "content": TEXTO}


async def test_request_parameters_and_timezone(schema):
    extractor, completions = _make(schema)
    await extractor.extract(TEXTO, RECEBIDO)
    call = completions.calls[0]
    assert call["model"] == "deepseek-flash"
    assert call["temperature"] == 0
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"][1] == {"role": "user", "content": TEXTO}
    # 22:30 UTC vira 06:30 em Xangai no dia seguinte.
    assert "06:30" in call["messages"][0]["content"]
    assert "2026-10-09" in call["messages"][0]["content"]


@pytest.mark.parametrize("texto", ["", "   ", "\n\t"])
async def test_blank_text_returns_default_error_without_calling_api(schema, texto):
    extractor, completions = _make(schema)
    result = await extractor.extract(texto, RECEBIDO)
    assert result.pagamento is None
    assert result.erro == MSG_DEFAULT_NOT_EXPENSE
    assert completions.calls == []


async def test_api_exception_is_chained_into_extraction_error(schema):
    extractor, _ = _make(schema, exc=RuntimeError("timeout"))
    with pytest.raises(ExtractionError) as info:
        await extractor.extract(TEXTO, RECEBIDO)
    assert isinstance(info.value.__cause__, RuntimeError)


# --- subtarefa 2: parsing robusto e `is_pagamento` ---------------------------------------------


def _payload(**overrides) -> str:
    import json

    data = {
        "is_pagamento": True,
        "valor_compra": 35,
        "motivo": None,
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


@pytest.mark.parametrize("content", ["não é json", "", "   ", None, 42, "[1, 2]", "null"])
async def test_invalid_content_returns_invalid_response(schema, content):
    extractor, _ = _make(schema, content=content)
    result = await extractor.extract(TEXTO, RECEBIDO)
    assert result.pagamento is None
    assert result.pergunta is None
    assert result.erro == MSG_INVALID_RESPONSE


async def test_code_fences_are_unwrapped(schema):
    extractor, _ = _make(schema, content="```json\n" + _payload() + "\n```")
    result = await extractor.extract(TEXTO, RECEBIDO)
    assert result.erro is None


async def test_response_without_choices_returns_invalid_response(schema):
    completions = _Completions(content=_payload())
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    async def _empty(**kwargs):
        return SimpleNamespace(choices=[])

    completions.create = _empty
    extractor = PaymentExtractor(api_key="k", schema=schema, client=client)
    assert (await extractor.extract(TEXTO, RECEBIDO)).erro == MSG_INVALID_RESPONSE


async def test_not_a_payment_uses_reason_then_default(schema):
    extractor, _ = _make(schema, content=_payload(is_pagamento=False, motivo="É um pedido."))
    result = await extractor.extract(TEXTO, RECEBIDO)
    assert result.pagamento is None
    assert result.erro == "É um pedido."

    extractor, _ = _make(schema, content=_payload(is_pagamento=False, motivo=None))
    assert (await extractor.extract(TEXTO, RECEBIDO)).erro == MSG_DEFAULT_NOT_EXPENSE
