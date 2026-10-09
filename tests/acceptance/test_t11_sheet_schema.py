from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.payment import Pagamento
from app.sheet_schema import Coluna, SchemaError, SheetSchema

pytestmark = pytest.mark.task("T11")

ROOT = Path(__file__).resolve().parents[2]
REGISTRADO = datetime(2026, 10, 8, 21, 5, tzinfo=ZoneInfo("Asia/Shanghai"))

BASE = {
    "aba": "Gastos",
    "colunas": [
        {"nome": "ID", "campo": "id", "tipo": "texto"},
        {"nome": "Data", "campo": "data", "tipo": "data"},
        {"nome": "Hora", "campo": "hora", "tipo": "hora", "obrigatoria": False},
        {"nome": "Descrição", "campo": "descricao", "tipo": "texto"},
        {"nome": "Método", "campo": "metodo_pagamento", "tipo": "enum"},
        {"nome": "Parcelas", "campo": "quant_parcelas", "tipo": "inteiro"},
        {"nome": "Valor", "campo": "valor_compra", "tipo": "moeda"},
        {"nome": "Valor parcela", "campo": "valor_parcela", "tipo": "moeda"},
        {"nome": "Moeda", "campo": "moeda", "tipo": "enum"},
        {"nome": "Usuário", "campo": "usuario", "tipo": "texto"},
        {"nome": "Registrado", "campo": "registrado_em", "tipo": "datahora"},
    ],
}
EXTRAS = {"id": "abc123", "usuario": "Vini", "registrado_em": REGISTRADO}


def schema(**changes):
    data = {"aba": BASE["aba"], "colunas": [dict(c) for c in BASE["colunas"]]}
    data.update(changes)
    return SheetSchema.from_dict(data)


def pagamento(**overrides):
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


def test_from_dict_builds_columns():
    s = schema()
    assert s.aba == "Gastos"
    assert s.colunas[0] == Coluna(nome="ID", campo="id", tipo="texto")
    assert s.colunas[2].obrigatoria is False


def test_load_from_yaml(tmp_path):
    path = tmp_path / "planilha.yaml"
    path.write_text(
        "aba: Gastos\ncolunas:\n  - nome: Data\n    campo: data\n    tipo: data\n"
        '    formato: "%Y-%m-%d"\n',
        encoding="utf-8",
    )
    s = SheetSchema.load(path)
    assert s.header() == ["Data"]
    assert s.colunas[0].formato == "%Y-%m-%d"


def test_load_missing_or_invalid_file(tmp_path):
    with pytest.raises(SchemaError):
        SheetSchema.load(tmp_path / "nao-existe.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("aba: [sem fechar\n", encoding="utf-8")
    with pytest.raises(SchemaError):
        SheetSchema.load(bad)


def test_default_schema_in_repo_is_valid():
    s = SheetSchema.load(ROOT / "config" / "planilha.yaml")
    campos = {c.campo for c in s.colunas}
    assert {"id", "data", "valor_compra", "metodo_pagamento", "quant_parcelas"} <= campos
    assert {"valor_parcela", "moeda", "descricao"} <= campos


@pytest.mark.parametrize(
    ("mutate", "nome"),
    [
        (lambda cols: cols.append({"nome": "Data", "campo": "hora", "tipo": "hora"}), "Data"),
        (lambda cols: cols.append({"nome": "Xyz", "campo": "inexistente", "tipo": "texto"}), "Xyz"),
        (lambda cols: cols.append({"nome": "Cor", "campo": "descricao", "tipo": "cor"}), "Cor"),
        (lambda cols: cols.append({"nome": "SemCampo", "tipo": "texto"}), "SemCampo"),
    ],
)
def test_invalid_columns_mention_the_column(mutate, nome):
    cols = [dict(c) for c in BASE["colunas"]]
    mutate(cols)
    with pytest.raises(SchemaError, match=nome):
        SheetSchema.from_dict({"aba": "Gastos", "colunas": cols})


@pytest.mark.parametrize(
    "data",
    [
        {"colunas": BASE["colunas"]},
        {"aba": "", "colunas": BASE["colunas"]},
        {"aba": "G"},
        {"aba": "G", "colunas": []},
    ],
)
def test_invalid_top_level(data):
    with pytest.raises(SchemaError):
        SheetSchema.from_dict(data)


def test_header():
    assert schema().header() == [c["nome"] for c in BASE["colunas"]]


def test_to_row_formats_each_type():
    row = schema().to_row(pagamento(), EXTRAS)
    assert row == [
        "abc123",
        "08/10/2026",
        "14:07",
        "tênis",
        "credito_parcelado",
        3,
        100.0,
        33.33,
        "BRL",
        "Vini",
        "2026-10-08T21:05:00+08:00",
    ]
    assert isinstance(row[6], float) and isinstance(row[5], int)


def test_to_row_custom_formats_and_optional_hour():
    cols = [
        {"nome": "Data", "campo": "data", "tipo": "data", "formato": "%Y-%m-%d"},
        {"nome": "Hora", "campo": "hora", "tipo": "hora", "obrigatoria": False},
        {"nome": "Reg", "campo": "registrado_em", "tipo": "datahora", "formato": "%d/%m %H:%M"},
    ]
    s = SheetSchema.from_dict({"aba": "G", "colunas": cols})
    row = s.to_row(pagamento(hora=None), {"registrado_em": REGISTRADO})
    assert row == ["2026-10-08", "", "08/10 21:05"]


def test_to_row_required_missing_raises():
    cols = [{"nome": "Hora obrigatória", "campo": "hora", "tipo": "hora"}]
    s = SheetSchema.from_dict({"aba": "G", "colunas": cols})
    with pytest.raises(SchemaError, match="Hora obrigatória"):
        s.to_row(pagamento(hora=None), {})


def test_to_row_missing_extra_raises():
    with pytest.raises(SchemaError):
        schema().to_row(pagamento(), {"id": "x", "usuario": "Vini"})


def test_prompt_context():
    text = schema().prompt_context()
    assert text.startswith("Colunas da planilha (aba Gastos):")
    assert "- Valor: campo valor_compra, tipo moeda" in text
    for col in BASE["colunas"]:
        assert f"- {col['nome']}: campo {col['campo']}, tipo {col['tipo']}" in text
    s = SheetSchema.from_dict(
        {"aba": "G", "colunas": [{"nome": "D", "campo": "data", "tipo": "data", "formato": "%Y"}]}
    )
    assert "- D: campo data, tipo data, formato %Y" in s.prompt_context()


def test_validate_header_ok():
    s = schema()
    s.validate_header(s.header())


def test_validate_header_points_to_divergence():
    s = schema()
    header = s.header()
    swapped = header[:]
    swapped[1], swapped[2] = swapped[2], swapped[1]
    with pytest.raises(SchemaError) as exc:
        s.validate_header(swapped)
    assert "2" in str(exc.value) and "Data" in str(exc.value)
    with pytest.raises(SchemaError):
        s.validate_header(header[:-1])
    with pytest.raises(SchemaError):
        s.validate_header([*header, "Extra"])
