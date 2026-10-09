import functools
import json
from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.domain import Category, Currency
from app.messages import MSG_PERGUNTA_PARCELAS, MSG_PERGUNTA_VALOR
from app.payment import MetodoPagamento
from app.payment_extractor import (
    MSG_DEFAULT_NOT_EXPENSE,
    MSG_INVALID_RESPONSE,
    ExtractionError,
    PaymentExtractor,
)
from app.prompts import PAYMENT_EXTRACTION_SYSTEM_PROMPT
from app.sheet_schema import SheetSchema

pytestmark = pytest.mark.task("T13")

# 2026-10-08 22:30 UTC == 2026-10-09 06:30 em Xangai
RECEBIDO = datetime(2026, 10, 8, 22, 30, 41, tzinfo=ZoneInfo("UTC"))
HOJE = date(2026, 10, 9)
AGORA = time(6, 30)


@functools.cache
def _schema():
    return SheetSchema.from_dict(
        {
            "aba": "Gastos",
            "colunas": [
                {"nome": "Data", "campo": "data", "tipo": "data"},
                {"nome": "Valor", "campo": "valor_compra", "tipo": "moeda"},
            ],
        }
    )


class FakeCompletions:
    def __init__(self, content=None, exc=None, response=None):
        self.content, self.exc, self.response, self.calls = content, exc, response, []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        if self.response is not None:
            return self.response
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make(content=None, **kw):
    completions = FakeCompletions(content, **kw)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return PaymentExtractor(api_key="k", schema=_schema(), client=client), completions


def payload(**overrides):
    data = {
        "is_pagamento": True,
        "valor_compra": 35,
        "moeda": "CNY",
        "metodo_pagamento": "alipay",
        "quant_parcelas": None,
        "categoria": "alimentação",
        "descricao": "almoço",
        "data": None,
        "hora": None,
        "motivo": None,
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


async def test_request_parameters():
    extractor, completions = make(payload())
    await extractor.extract("almoço 35 kuai alipay", RECEBIDO)
    call = completions.calls[0]
    assert call["model"] == "deepseek-flash"
    assert call["temperature"] == 0
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"] == [
        {
            "role": "system",
            "content": PAYMENT_EXTRACTION_SYSTEM_PROMPT.format(
                agora="06:30",
                hoje="2026-10-09",
                moeda_padrao="CNY",
                schema=_schema().prompt_context(),
            ),
        },
        {"role": "user", "content": "almoço 35 kuai alipay"},
    ]


async def test_simple_payment_uses_message_date_and_time():
    extractor, _ = make(payload())
    result = await extractor.extract("almoço 35 kuai alipay", RECEBIDO)
    p = result.pagamento
    assert result.erro is None and result.pergunta is None
    assert p.valor_compra == Decimal("35.00")
    assert p.moeda is Currency.CNY
    assert p.metodo_pagamento is MetodoPagamento.ALIPAY
    assert p.categoria is Category.ALIMENTACAO
    assert p.data == HOJE
    assert p.hora == AGORA
    assert p.texto_original == "almoço 35 kuai alipay"


async def test_installments_are_computed_by_the_app():
    extractor, _ = make(
        payload(
            valor_compra=3000,
            moeda="BRL",
            metodo_pagamento="credito_parcelado",
            quant_parcelas=10,
            categoria="compras",
            descricao="celular",
            valor_parcela=999,
        )
    )
    result = await extractor.extract("celular 3.000 reais em 10x no crédito", RECEBIDO)
    p = result.pagamento
    assert p.metodo_pagamento is MetodoPagamento.CREDITO_PARCELADO
    assert p.quant_parcelas == 10
    assert p.valor_parcela == Decimal("300.00")


async def test_explicit_date_and_time():
    extractor, _ = make(payload(data="2026-10-08", hora="23:15"))
    p = (await extractor.extract("ontem às 23h15 jantar 35", RECEBIDO)).pagamento
    assert p.data == date(2026, 10, 8)
    assert p.hora == time(23, 15)


async def test_past_date_without_time_has_no_time():
    extractor, _ = make(payload(data="2026-10-07"))
    p = (await extractor.extract("anteontem jantar 35", RECEBIDO)).pagamento
    assert p.data == date(2026, 10, 7)
    assert p.hora is None


async def test_invalid_date_and_time_fall_back_to_message():
    extractor, _ = make(payload(data="ontem", hora="25:99"))
    p = (await extractor.extract("jantar 35", RECEBIDO)).pagamento
    assert p.data == HOJE
    assert p.hora == AGORA


async def test_missing_value_asks_question():
    extractor, _ = make(payload(valor_compra=None))
    result = await extractor.extract("paguei o táxi", RECEBIDO)
    assert result.pagamento is None
    assert result.pergunta == MSG_PERGUNTA_VALOR


async def test_installments_without_count_asks_question():
    extractor, _ = make(payload(metodo_pagamento="credito_parcelado", quant_parcelas=None))
    result = await extractor.extract("comprei parcelado", RECEBIDO)
    assert result.pagamento is None
    assert result.pergunta == MSG_PERGUNTA_PARCELAS


async def test_missing_description_uses_text():
    texto = "  80 kuai " + "x" * 100
    extractor, _ = make(payload(descricao=None))
    p = (await extractor.extract(texto, RECEBIDO)).pagamento
    assert p.descricao == texto.strip()[:80]


async def test_missing_currency_uses_default():
    completions = FakeCompletions(payload(moeda=None))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    extractor = PaymentExtractor(
        api_key="k", schema=_schema(), client=client, default_currency="BRL"
    )
    p = (await extractor.extract("pão 10", RECEBIDO)).pagamento
    assert p.moeda is Currency.BRL


async def test_not_a_payment():
    extractor, _ = make(payload(is_pagamento=False, valor_compra=None, motivo="É uma saudação."))
    result = await extractor.extract("oi", RECEBIDO)
    assert result.pagamento is None and result.erro == "É uma saudação."
    extractor, _ = make(payload(is_pagamento=False, motivo=None))
    assert (await extractor.extract("oi", RECEBIDO)).erro == MSG_DEFAULT_NOT_EXPENSE


@pytest.mark.parametrize("content", ["não é json", "", None, "[1, 2]"])
async def test_invalid_content(content):
    extractor, _ = make(content)
    result = await extractor.extract("jantar 35", RECEBIDO)
    assert result.pagamento is None and result.erro == MSG_INVALID_RESPONSE


async def test_code_fences_are_accepted():
    extractor, _ = make("```json\n" + payload() + "\n```")
    assert (await extractor.extract("jantar 35", RECEBIDO)).pagamento is not None


async def test_response_without_choices():
    extractor, _ = make(response=SimpleNamespace(choices=[]))
    assert (await extractor.extract("jantar 35", RECEBIDO)).erro == MSG_INVALID_RESPONSE


async def test_invalid_fields_return_invalid_response():
    extractor, _ = make(payload(valor_compra=-5))
    assert (await extractor.extract("jantar", RECEBIDO)).erro == MSG_INVALID_RESPONSE


@pytest.mark.parametrize("texto", ["", "   "])
async def test_empty_text_does_not_call_api(texto):
    extractor, completions = make(payload())
    result = await extractor.extract(texto, RECEBIDO)
    assert result.erro == MSG_DEFAULT_NOT_EXPENSE
    assert completions.calls == []


async def test_api_error_raises():
    extractor, _ = make(exc=RuntimeError("timeout"))
    with pytest.raises(ExtractionError):
        await extractor.extract("jantar 35", RECEBIDO)


def test_default_client():
    from openai import AsyncOpenAI

    extractor = PaymentExtractor(api_key="k", schema=_schema())
    assert isinstance(extractor.client, AsyncOpenAI)
    assert "api.deepseek.com" in str(extractor.client.base_url)
