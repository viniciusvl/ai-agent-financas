import functools
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.messages import MSG_LEITURA_NAO_SUPORTADA, MSG_NENHUM_GASTO, MSG_NENHUMA_PARCELA
from app.prompts import READ_AGENT_SYSTEM_PROMPT
from app.queries import (
    GastosRepository,
    Registro,
    format_totais,
    format_valor,
    parcelas_futuras,
    parse_rows,
    total_periodo,
    total_por_categoria,
    total_por_metodo,
    ultimos,
)
from app.read_agent import TOOLS, ReadAgent, ReadError
from app.sheet_schema import SheetSchema

pytestmark = pytest.mark.task("T15")

D = Decimal
SCHEMA_DICT = {
    "aba": "Gastos",
    "colunas": [
        {"nome": "ID", "campo": "id", "tipo": "texto"},
        {"nome": "Data", "campo": "data", "tipo": "data", "formato": "%Y-%m-%d"},
        {"nome": "Descrição", "campo": "descricao", "tipo": "texto"},
        {"nome": "Categoria", "campo": "categoria", "tipo": "enum"},
        {"nome": "Método", "campo": "metodo_pagamento", "tipo": "enum"},
        {"nome": "Parcelas", "campo": "quant_parcelas", "tipo": "inteiro"},
        {"nome": "Valor", "campo": "valor_compra", "tipo": "moeda"},
        {"nome": "Moeda", "campo": "moeda", "tipo": "enum"},
    ],
}


@functools.cache
def _schema():
    return SheetSchema.from_dict(SCHEMA_DICT)


ROWS = [
    ["a1", "2026-10-05", "almoço", "alimentação", "alipay", 1, 35, "CNY"],
    ["a2", "2026-10-06", "táxi", "transporte", "wechat_pay", "1", "80,50", "CNY"],
    ["a3", "2026-10-06", "tênis", "compras", "credito_parcelado", 3, 300, "BRL"],
    ["", "", "", "", "", "", "", ""],
    ["a4", "data ruim", "x", "outros", "outro", 1, 10, "CNY"],
    ["a5", "07/10/2026", "museu", "passeios", "dinheiro", 1.0, "1.234,56", "CNY"],
    ["a6", "2026-10-07", "valor ruim", "outros", "outro", 1, "abc", "CNY"],
    ["a7", "2026-09-20", "mala", "compras", "credito_parcelado", 2, "100.01", "BRL"],
]


@functools.cache
def _regs():
    return parse_rows(_schema(), ROWS)


# --- formatação ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("moeda", "valor", "esperado"),
    [
        ("CNY", D("1234.56"), "¥ 1.234,56"),
        ("BRL", D("0.5"), "R$ 0,50"),
        ("USD", D("1000000"), "US$ 1.000.000,00"),
        ("EUR", D("3"), "EUR 3,00"),
    ],
)
def test_format_valor(moeda, valor, esperado):
    assert format_valor(moeda, valor) == esperado


def test_format_totais():
    assert format_totais({"CNY": D("10"), "BRL": D("2.5")}) == "R$ 2,50 + ¥ 10,00"
    assert format_totais({}) == MSG_NENHUM_GASTO


# --- parse_rows ---------------------------------------------------------------------------------


def test_parse_rows_skips_invalid_and_parses_formats(caplog):
    caplog.set_level(logging.WARNING)
    regs = parse_rows(_schema(), ROWS)
    assert [r.descricao for r in regs] == ["almoço", "táxi", "tênis", "museu", "mala"]
    assert regs[1] == Registro(
        data=date(2026, 10, 6),
        valor_compra=D("80.50"),
        moeda="CNY",
        categoria="transporte",
        metodo_pagamento="wechat_pay",
        quant_parcelas=1,
        descricao="táxi",
    )
    assert regs[3].data == date(2026, 10, 7)
    assert regs[3].valor_compra == D("1234.56")
    assert regs[3].quant_parcelas == 1
    assert regs[4].valor_compra == D("100.01")
    assert caplog.records, "linhas inválidas devem gerar WARNING"


def test_parse_rows_with_minimal_schema_uses_defaults():
    schema = SheetSchema.from_dict(
        {
            "aba": "G",
            "colunas": [
                {"nome": "Data", "campo": "data", "tipo": "data"},
                {"nome": "Valor", "campo": "valor_compra", "tipo": "moeda"},
            ],
        }
    )
    regs = parse_rows(schema, [["08/10/2026", "R$ 10,00"], [date(2026, 10, 9), 5]])
    assert regs[0] == Registro(data=date(2026, 10, 8), valor_compra=D("10.00"))
    assert regs[1].data == date(2026, 10, 9) and regs[1].moeda == "CNY"


# --- consultas ----------------------------------------------------------------------------------


def test_total_periodo_inclusive_by_currency():
    assert total_periodo(_regs(), date(2026, 10, 5), date(2026, 10, 6)) == {
        "CNY": D("115.50"),
        "BRL": D("300.00"),
    }
    assert total_periodo(_regs(), date(2026, 1, 1), date(2026, 1, 2)) == {}


def test_total_por_categoria_e_metodo():
    inicio, fim = date(2026, 10, 1), date(2026, 10, 31)
    assert total_por_categoria(_regs(), inicio, fim) == {
        "alimentação": {"CNY": D("35.00")},
        "transporte": {"CNY": D("80.50")},
        "compras": {"BRL": D("300.00")},
        "passeios": {"CNY": D("1234.56")},
    }
    assert total_por_metodo(_regs(), inicio, fim)["credito_parcelado"] == {"BRL": D("300.00")}


def test_ultimos_orders_by_date_desc_then_reverse_sheet_order():
    assert [r.descricao for r in ultimos(_regs(), 3)] == ["museu", "tênis", "táxi"]
    assert len(ultimos(_regs(), 50)) == 5


def test_parcelas_futuras():
    # tênis: 06/10, 300 em 3x → 11/2026, 12/2026, 01/2027 de 100,00
    # mala: 20/09, 100,01 em 2x → 10/2026 50,01 e 11/2026 50,00
    assert parcelas_futuras(_regs(), date(2026, 10, 9)) == {
        "2026-10": {"BRL": D("50.01")},
        "2026-11": {"BRL": D("150.00")},
        "2026-12": {"BRL": D("100.00")},
        "2027-01": {"BRL": D("100.00")},
    }
    assert parcelas_futuras(_regs(), date(2027, 2, 1)) == {}


# --- GastosRepository ---------------------------------------------------------------------------


class FakeWorksheet:
    def __init__(self, rows, fail=False):
        self.rows, self.fail, self.calls = rows, fail, []

    def get_all_values(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("down")
        return [list(r) for r in self.rows]


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_repository_reads_with_render_options_and_caches():
    ws, clock = FakeWorksheet([_schema().header(), *ROWS]), Clock()
    repo = GastosRepository(ws, _schema(), ttl_seconds=60, clock=clock)
    assert repo.registros() == _regs()
    assert ws.calls == [
        {"value_render_option": "UNFORMATTED_VALUE", "date_time_render_option": "FORMATTED_STRING"}
    ]
    clock.t = 59
    repo.registros()
    assert len(ws.calls) == 1
    clock.t = 61
    repo.registros()
    assert len(ws.calls) == 2
    repo.invalidate()
    repo.registros()
    assert len(ws.calls) == 3


def test_repository_errors():
    with pytest.raises(ReadError):
        GastosRepository(FakeWorksheet([], fail=True), _schema()).registros()


# --- ReadAgent ----------------------------------------------------------------------------------

AGORA = datetime(2026, 10, 8, 23, 30, tzinfo=ZoneInfo("UTC"))  # 09/10 (sexta) em Xangai


class FakeRepo:
    def __init__(self, regs=None, fail=False):
        self.regs, self.fail = (_regs() if regs is None else regs), fail

    def registros(self):
        if self.fail:
            raise ReadError("down")
        return self.regs


class FakeCompletions:
    def __init__(self, tool=None, args=None, raw_args=None, exc=None, no_tool=False):
        self.tool, self.args, self.raw_args = tool, args, raw_args
        self.exc, self.no_tool, self.calls = exc, no_tool, []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        if self.no_tool:
            message = SimpleNamespace(content="não sei", tool_calls=None)
        else:
            arguments = self.raw_args if self.raw_args is not None else json.dumps(self.args or {})
            call = SimpleNamespace(
                id="c1",
                type="function",
                function=SimpleNamespace(name=self.tool, arguments=arguments),
            )
            message = SimpleNamespace(content=None, tool_calls=[call])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def agent(repo=None, **kw):
    completions = FakeCompletions(**kw)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return ReadAgent(api_key="k", repo=repo or FakeRepo(), client=client), completions


def test_tools_definition():
    names = {t["function"]["name"] for t in TOOLS}
    assert names == {
        "total_periodo",
        "total_por_categoria",
        "total_por_metodo",
        "ultimos_gastos",
        "parcelas_futuras",
    }
    assert all(t["type"] == "function" for t in TOOLS)
    periodo = next(t for t in TOOLS if t["function"]["name"] == "total_periodo")
    assert set(periodo["function"]["parameters"]["required"]) == {"inicio", "fim"}


async def test_request_parameters():
    ag, completions = agent(
        tool="total_periodo", args={"inicio": "2026-10-05", "fim": "2026-10-06"}
    )
    await ag.answer("quanto gastei?", AGORA)
    call = completions.calls[0]
    assert call["model"] == "deepseek-flash"
    assert call["temperature"] == 0
    assert call["tools"] == TOOLS
    assert call["tool_choice"] == "auto"
    assert call["messages"] == [
        {
            "role": "system",
            "content": READ_AGENT_SYSTEM_PROMPT.format(hoje="2026-10-09", dia_semana="sexta-feira"),
        },
        {"role": "user", "content": "quanto gastei?"},
    ]


async def test_total_periodo_answer():
    ag, _ = agent(tool="total_periodo", args={"inicio": "2026-10-06", "fim": "2026-10-05"})
    assert (
        await ag.answer("?", AGORA) == "💰 Total de 05/10/2026 a 06/10/2026: R$ 300,00 + ¥ 115,50"
    )


async def test_total_por_categoria_answer():
    ag, _ = agent(tool="total_por_categoria", args={"inicio": "2026-10-05", "fim": "2026-10-05"})
    assert await ag.answer("?", AGORA) == (
        "📊 Gastos por categoria de 05/10/2026 a 05/10/2026:\n• alimentação: ¥ 35,00"
    )
    ag, _ = agent(tool="total_por_categoria", args={"inicio": "2025-01-01", "fim": "2025-01-02"})
    assert await ag.answer("?", AGORA) == (
        f"📊 Gastos por categoria de 01/01/2025 a 02/01/2025:\n{MSG_NENHUM_GASTO}"
    )


async def test_total_por_metodo_answer():
    ag, _ = agent(tool="total_por_metodo", args={"inicio": "2026-10-06", "fim": "2026-10-06"})
    assert await ag.answer("?", AGORA) == (
        "💳 Gastos por forma de pagamento de 06/10/2026 a 06/10/2026:\n"
        "• credito_parcelado: R$ 300,00\n"
        "• wechat_pay: ¥ 80,50"
    )


async def test_ultimos_answer_and_limits():
    ag, _ = agent(tool="ultimos_gastos", args={"n": 2})
    assert await ag.answer("?", AGORA) == (
        "🧾 Últimos gastos:\n• 07/10 — museu — ¥ 1.234,56\n• 06/10 — tênis — R$ 300,00"
    )
    ag, _ = agent(tool="ultimos_gastos", args={})
    assert (await ag.answer("?", AGORA)).count("\n•") == 5
    ag, _ = agent(tool="ultimos_gastos", args={"n": 500}, repo=FakeRepo(regs=_regs() * 10))
    assert (await ag.answer("?", AGORA)).count("\n•") == 20
    ag, _ = agent(tool="ultimos_gastos", args={"n": 3}, repo=FakeRepo(regs=[]))
    assert await ag.answer("?", AGORA) == f"🧾 Últimos gastos:\n{MSG_NENHUM_GASTO}"


async def test_parcelas_futuras_answer():
    ag, _ = agent(tool="parcelas_futuras", args={})
    assert await ag.answer("?", AGORA) == (
        "📅 Parcelas futuras:\n"
        "• 10/2026: R$ 50,01\n"
        "• 11/2026: R$ 150,00\n"
        "• 12/2026: R$ 100,00\n"
        "• 01/2027: R$ 100,00"
    )
    ag, _ = agent(tool="parcelas_futuras", args={}, repo=FakeRepo(regs=[]))
    assert await ag.answer("?", AGORA) == f"📅 Parcelas futuras:\n{MSG_NENHUMA_PARCELA}"


@pytest.mark.parametrize(
    "kw",
    [
        {"no_tool": True},
        {"tool": "apagar_tudo", "args": {}},
        {"tool": "total_periodo", "raw_args": "{não é json"},
        {"tool": "total_periodo", "args": {"inicio": "ontem", "fim": "2026-10-09"}},
        {"tool": "total_periodo", "args": {"inicio": "2026-10-01"}},
    ],
)
async def test_unsupported_or_malformed(kw):
    ag, _ = agent(**kw)
    assert await ag.answer("qual a capital da China?", AGORA) == MSG_LEITURA_NAO_SUPORTADA


async def test_llm_error_raises_read_error():
    ag, _ = agent(exc=RuntimeError("timeout"))
    with pytest.raises(ReadError):
        await ag.answer("?", AGORA)


async def test_repo_error_raises_read_error():
    ag, _ = agent(tool="ultimos_gastos", args={}, repo=FakeRepo(fail=True))
    with pytest.raises(ReadError):
        await ag.answer("?", AGORA)


def test_default_client():
    from openai import AsyncOpenAI

    assert isinstance(ReadAgent(api_key="k", repo=FakeRepo()).client, AsyncOpenAI)
