"""Testes unitários de `app.queries` (formatação e parse). Spec: T15."""

import logging
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.messages import MSG_NENHUM_GASTO
from app.queries import Registro, format_totais, format_valor, parse_rows
from app.sheet_schema import SheetSchema

D = Decimal

SCHEMA = SheetSchema.from_dict(
    {
        "aba": "G",
        "colunas": [
            {"nome": "Data", "campo": "data", "tipo": "data", "formato": "%d/%m/%Y"},
            {"nome": "Descrição", "campo": "descricao", "tipo": "texto"},
            {"nome": "Categoria", "campo": "categoria", "tipo": "enum"},
            {"nome": "Método", "campo": "metodo_pagamento", "tipo": "enum"},
            {"nome": "Parcelas", "campo": "quant_parcelas", "tipo": "inteiro"},
            {"nome": "Valor", "campo": "valor_compra", "tipo": "moeda"},
            {"nome": "Moeda", "campo": "moeda", "tipo": "enum"},
        ],
    }
)


@pytest.mark.parametrize(
    ("moeda", "valor", "esperado"),
    [
        ("CNY", D("0"), "¥ 0,00"),
        ("BRL", D("1234567.8"), "R$ 1.234.567,80"),
        ("USD", D("0.01"), "US$ 0,01"),
        ("JPY", D("42"), "JPY 42,00"),
    ],
)
def test_format_valor(moeda, valor, esperado):
    assert format_valor(moeda, valor) == esperado


def test_format_totais_ordena_por_moeda():
    assert format_totais({"USD": D("1"), "CNY": D("2"), "BRL": D("3")}) == (
        "R$ 3,00 + ¥ 2,00 + US$ 1,00"
    )
    assert format_totais({}) == MSG_NENHUM_GASTO


def test_parse_rows_aceita_simbolos_e_formatos():
    rows = [
        ["08/10/2026", "almoço", "alimentação", "alipay", "2", "¥ 1.234,56", "CNY"],
        [datetime(2026, 10, 9, 12, 0), "café", "alimentação", "dinheiro", 1.0, "R$ 10,00", "BRL"],
    ]
    regs = parse_rows(SCHEMA, rows)
    assert regs[0] == Registro(
        data=date(2026, 10, 8),
        valor_compra=D("1234.56"),
        moeda="CNY",
        categoria="alimentação",
        metodo_pagamento="alipay",
        quant_parcelas=2,
        descricao="almoço",
    )
    assert regs[1].data == date(2026, 10, 9)
    assert regs[1].valor_compra == D("10.00")
    assert regs[1].moeda == "BRL"


def test_parse_rows_colunas_ausentes_usam_padroes():
    schema = SheetSchema.from_dict(
        {
            "aba": "G",
            "colunas": [
                {"nome": "Data", "campo": "data", "tipo": "data", "formato": "%Y-%m-%d"},
                {"nome": "Valor", "campo": "valor_compra", "tipo": "moeda"},
            ],
        }
    )
    (reg,) = parse_rows(schema, [["2026-10-08", 35]])
    assert reg == Registro(data=date(2026, 10, 8), valor_compra=D("35.00"))


def test_parse_rows_linha_curta_usa_padroes():
    (reg,) = parse_rows(SCHEMA, [["2026-10-08", "curta", "outros", "outro", 1, 35]])
    assert reg.descricao == "curta"
    assert reg.valor_compra == D("35.00")
    assert reg.moeda == "CNY"


@pytest.mark.parametrize(
    "row",
    [
        ["2026-10-08", "ok", "outros", "outro", 1, 0, "CNY"],
        ["2026-10-08", "ok", "outros", "outro", 1, "-5", "CNY"],
        ["2026-10-08", "ok", "outros", "outro", 1, "sem numero", "CNY"],
    ],
)
def test_parse_rows_ignora_valor_invalido(row, caplog):
    caplog.set_level(logging.WARNING)
    assert parse_rows(SCHEMA, [row]) == []
    assert caplog.records


def test_parse_rows_parcelas_invalidas_viram_1():
    (reg,) = parse_rows(SCHEMA, [["2026-10-08", "x", "outros", "outro", "abc", 5, "CNY"]])
    assert reg.quant_parcelas == 1
