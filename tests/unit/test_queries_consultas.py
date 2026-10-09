"""Testes unitários das consultas e do repositório de `app.queries`. Spec: T15."""

from datetime import date
from decimal import Decimal

import pytest

from app.queries import (
    GastosRepository,
    ReadError,
    Registro,
    parcelas_futuras,
    total_periodo,
    total_por_categoria,
    total_por_metodo,
    ultimos,
)
from app.sheet_schema import SheetSchema

D = Decimal

SCHEMA = SheetSchema.from_dict(
    {
        "aba": "G",
        "colunas": [
            {"nome": "Data", "campo": "data", "tipo": "data", "formato": "%Y-%m-%d"},
            {"nome": "Descrição", "campo": "descricao", "tipo": "texto"},
            {"nome": "Categoria", "campo": "categoria", "tipo": "enum"},
            {"nome": "Método", "campo": "metodo_pagamento", "tipo": "enum"},
            {"nome": "Parcelas", "campo": "quant_parcelas", "tipo": "inteiro"},
            {"nome": "Valor", "campo": "valor_compra", "tipo": "moeda"},
            {"nome": "Moeda", "campo": "moeda", "tipo": "enum"},
        ],
    }
)

REGS = [
    Registro(date(2026, 10, 5), D("35.00"), "CNY", "alimentação", "alipay", 1, "almoço"),
    Registro(date(2026, 10, 6), D("80.50"), "CNY", "transporte", "wechat_pay", 1, "táxi"),
    Registro(date(2026, 10, 6), D("300.00"), "BRL", "compras", "credito_parcelado", 3, "tênis"),
    Registro(date(2026, 9, 20), D("100.01"), "BRL", "compras", "credito_parcelado", 2, "mala"),
]


def test_total_periodo_e_inclusivo_por_moeda():
    assert total_periodo(REGS, date(2026, 10, 5), date(2026, 10, 6)) == {
        "CNY": D("115.50"),
        "BRL": D("300.00"),
    }
    assert total_periodo(REGS, date(2026, 1, 1), date(2026, 1, 2)) == {}


def test_total_por_categoria_e_metodo():
    cats = total_por_categoria(REGS, date(2026, 10, 1), date(2026, 10, 31))
    assert cats["transporte"] == {"CNY": D("80.50")}
    assert cats["compras"] == {"BRL": D("300.00")}
    assert cats["alimentação"] == {"CNY": D("35.00")}

    metodos = total_por_metodo(REGS, date(2026, 10, 1), date(2026, 10, 31))
    assert metodos["credito_parcelado"] == {"BRL": D("300.00")}
    assert metodos["alipay"] == {"CNY": D("35.00")}


def test_ultimos_empate_inverte_ordem_da_planilha():
    assert [r.descricao for r in ultimos(REGS, 3)] == ["tênis", "táxi", "almoço"]
    assert len(ultimos(REGS, 50)) == 4
    assert ultimos(REGS, 0) == []
    assert ultimos(REGS, -3) == []


def test_parcelas_futuras_mes_da_compra_mais_k():
    assert parcelas_futuras(REGS, date(2026, 10, 9)) == {
        "2026-10": {"BRL": D("50.01")},
        "2026-11": {"BRL": D("150.00")},
        "2026-12": {"BRL": D("100.00")},
        "2027-01": {"BRL": D("100.00")},
    }
    assert parcelas_futuras(REGS, date(2027, 2, 1)) == {}
    assert list(parcelas_futuras(REGS, date(2026, 10, 9))) == [
        "2026-10",
        "2026-11",
        "2026-12",
        "2027-01",
    ]


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


def _rows():
    return [
        SCHEMA.header(),
        ["2026-10-05", "almoço", "alimentação", "alipay", 1, 35, "CNY"],
        ["2026-10-06", "táxi", "transporte", "wechat_pay", 1, "80,50", "CNY"],
    ]


def test_repositorio_usa_render_options_e_cache_por_ttl():
    ws, clock = FakeWorksheet(_rows()), Clock()
    repo = GastosRepository(ws, SCHEMA, ttl_seconds=60, clock=clock)
    assert len(repo.registros()) == 2
    assert ws.calls == [
        {"value_render_option": "UNFORMATTED_VALUE", "date_time_render_option": "SERIAL_NUMBER"}
    ]
    clock.t = 59
    repo.registros()
    assert len(ws.calls) == 1
    clock.t = 60
    repo.registros()
    assert len(ws.calls) == 2
    repo.invalidate()
    repo.registros()
    assert len(ws.calls) == 3


def test_repositorio_erro_do_worksheet_vira_read_error():
    with pytest.raises(ReadError):
        GastosRepository(FakeWorksheet([], fail=True), SCHEMA).registros()
