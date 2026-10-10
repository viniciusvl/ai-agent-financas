"""Testes unitários de `SheetSchema.header`/`to_row` (spec T11, subtarefa 2)."""

from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.payment import Pagamento
from app.sheet_schema import SchemaError, SheetSchema

REGISTRADO = datetime(2026, 10, 8, 21, 5, tzinfo=ZoneInfo("America/Sao_Paulo"))


def _schema(*colunas):
    return SheetSchema.from_dict({"aba": "G", "colunas": list(colunas)})


def _pagamento(**overrides):
    data = dict(
        metodo_pagamento="credito_parcelado",
        quant_parcelas=3,
        data=date(2026, 10, 8),
        hora=time(14, 7),
        valor_compra=Decimal("100"),
        moeda="BRL",
        descricao="tênis",
    )
    data.update(overrides)
    return Pagamento(**data)


def test_header_returns_names_in_order():
    s = _schema(
        {"nome": "ID", "campo": "id", "tipo": "texto"},
        {"nome": "Data", "campo": "data", "tipo": "data"},
    )
    assert s.header() == ["ID", "Data"]


def test_to_row_formats_each_type():
    s = _schema(
        {"nome": "ID", "campo": "id", "tipo": "texto"},
        {"nome": "Data", "campo": "data", "tipo": "data"},
        {"nome": "Hora", "campo": "hora", "tipo": "hora", "obrigatoria": False},
        {"nome": "Descrição", "campo": "descricao", "tipo": "texto"},
        {"nome": "Método", "campo": "metodo_pagamento", "tipo": "enum"},
        {"nome": "Parcelas", "campo": "quant_parcelas", "tipo": "inteiro"},
        {"nome": "Valor", "campo": "valor_compra", "tipo": "moeda"},
        {"nome": "Moeda", "campo": "moeda", "tipo": "enum"},
        {"nome": "Registrado", "campo": "registrado_em", "tipo": "datahora"},
    )
    row = s.to_row(_pagamento(), {"id": "abc", "registrado_em": REGISTRADO})
    assert row == [
        "abc",
        "08/10/2026",
        "14:07",
        "tênis",
        "credito_parcelado",
        3,
        100.0,
        "BRL",
        "2026-10-08T21:05:00-03:00",
    ]
    assert isinstance(row[5], int)
    assert isinstance(row[6], float)


def test_to_row_custom_formats_and_optional_none():
    s = _schema(
        {"nome": "Data", "campo": "data", "tipo": "data", "formato": "%Y-%m-%d"},
        {"nome": "Hora", "campo": "hora", "tipo": "hora", "obrigatoria": False},
        {"nome": "Reg", "campo": "registrado_em", "tipo": "datahora", "formato": "%d/%m %H:%M"},
    )
    row = s.to_row(_pagamento(hora=None), {"registrado_em": REGISTRADO})
    assert row == ["2026-10-08", "", "08/10 21:05"]


def test_to_row_optional_empty_texto_is_empty_string():
    s = _schema({"nome": "Texto", "campo": "texto_original", "tipo": "texto", "obrigatoria": False})
    assert s.to_row(_pagamento(), {}) == [""]


def test_to_row_none_texto_becomes_empty_string():
    s = _schema({"nome": "Texto", "campo": "texto_original", "tipo": "texto", "obrigatoria": False})
    pagamento = Pagamento.model_construct(texto_original=None)
    assert s.to_row(pagamento, {}) == [""]


def test_to_row_required_none_raises_with_column_name():
    s = _schema({"nome": "Hora obrigatória", "campo": "hora", "tipo": "hora"})
    with pytest.raises(SchemaError, match="Hora obrigatória"):
        s.to_row(_pagamento(hora=None), {})


def test_to_row_missing_extra_raises():
    s = _schema({"nome": "Usuário", "campo": "usuario", "tipo": "texto"})
    with pytest.raises(SchemaError, match="Usuário"):
        s.to_row(_pagamento(), {})


def test_to_row_enum_uses_enum_value():
    s = _schema({"nome": "Moeda", "campo": "moeda", "tipo": "enum"})
    assert s.to_row(_pagamento(), {}) == ["BRL"]
