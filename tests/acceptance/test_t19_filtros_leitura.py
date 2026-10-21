import json
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.domain import Category
from app.messages import MSG_LEITURA_NAO_SUPORTADA
from app.payment import MetodoPagamento
from app.queries import Registro, total_periodo
from app.read_agent import TOOLS, ReadAgent

pytestmark = pytest.mark.task("T19")

D = Decimal
INICIO, FIM = date(2026, 10, 5), date(2026, 10, 6)
REGS = [
    Registro(date(2026, 10, 5), D("35"), "BRL", "alimentação", "pix", 1, "almoço"),
    Registro(date(2026, 10, 6), D("80"), "BRL", "transporte", "pix", 1, "uber"),
    Registro(date(2026, 10, 6), D("20"), "USD", "alimentação", "debito", 1, "lanche"),
    Registro(date(2026, 10, 9), D("99"), "BRL", "alimentação", "pix", 1, "fora do período"),
]
AGORA = datetime(2026, 10, 9, 15, 0, tzinfo=ZoneInfo("UTC"))


def test_total_periodo_com_filtros():
    assert total_periodo(REGS, INICIO, FIM) == {"BRL": D("115"), "USD": D("20")}
    assert total_periodo(REGS, INICIO, FIM, categoria="alimentação") == {
        "BRL": D("35"),
        "USD": D("20"),
    }
    assert total_periodo(REGS, INICIO, FIM, metodo_pagamento="pix") == {"BRL": D("115")}
    assert total_periodo(REGS, INICIO, FIM, categoria="alimentação", metodo_pagamento="pix") == {
        "BRL": D("35")
    }
    assert total_periodo(REGS, INICIO, FIM, categoria="compras") == {}


def test_tool_total_periodo_tem_filtros_opcionais():
    tool = next(t for t in TOOLS if t["function"]["name"] == "total_periodo")
    params = tool["function"]["parameters"]
    assert set(params["required"]) == {"inicio", "fim"}
    assert params["properties"]["categoria"]["enum"] == [c.value for c in Category]
    assert params["properties"]["metodo_pagamento"]["enum"] == [m.value for m in MetodoPagamento]


class FakeRepo:
    def registros(self):
        return REGS


class FakeCompletions:
    def __init__(self, args):
        self.args = args

    async def create(self, **kwargs):
        call = SimpleNamespace(
            id="c1",
            type="function",
            function=SimpleNamespace(name="total_periodo", arguments=json.dumps(self.args)),
        )
        message = SimpleNamespace(content=None, tool_calls=[call])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def agente(args):
    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(args)))
    return ReadAgent(api_key="k", repo=FakeRepo(), client=client, timezone="America/Sao_Paulo")


PERIODO = {"inicio": "2026-10-05", "fim": "2026-10-06"}


@pytest.mark.parametrize(
    ("filtros", "esperado"),
    [
        ({}, "💰 Total de 05/10/2026 a 06/10/2026: R$ 115,00 + US$ 20,00"),
        (
            {"categoria": "alimentação"},
            "💰 Total de 05/10/2026 a 06/10/2026 (categoria alimentação): R$ 35,00 + US$ 20,00",
        ),
        (
            {"metodo_pagamento": "pix"},
            "💰 Total de 05/10/2026 a 06/10/2026 (pagamento pix): R$ 115,00",
        ),
        (
            {"categoria": "alimentação", "metodo_pagamento": "pix"},
            "💰 Total de 05/10/2026 a 06/10/2026 (categoria alimentação, pagamento pix): R$ 35,00",
        ),
    ],
)
async def test_resposta_com_filtros(filtros, esperado):
    assert await agente({**PERIODO, **filtros}).answer("?", AGORA) == esperado


@pytest.mark.parametrize("filtros", [{"categoria": "xyz"}, {"metodo_pagamento": "cheque"}])
async def test_filtro_invalido(filtros):
    assert await agente({**PERIODO, **filtros}).answer("?", AGORA) == MSG_LEITURA_NAO_SUPORTADA
