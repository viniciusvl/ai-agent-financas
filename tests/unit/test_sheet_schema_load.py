"""Testes unitários de `SheetSchema.from_dict`/`load` (spec T11, subtarefa 1)."""

import pytest

from app.sheet_schema import SchemaError, SheetSchema


def _data(**changes):
    data = {
        "aba": "Gastos",
        "colunas": [
            {"nome": "Data", "campo": "data", "tipo": "data"},
            {"nome": "Valor", "campo": "valor_compra", "tipo": "moeda"},
        ],
    }
    data.update(changes)
    return data


def test_from_dict_builds_columns_and_defaults():
    s = SheetSchema.from_dict(_data())
    assert s.aba == "Gastos"
    assert [c.nome for c in s.colunas] == ["Data", "Valor"]
    assert isinstance(s.colunas, tuple)
    # formato opcional (None) e obrigatoria padrão True.
    assert s.colunas[0].formato is None
    assert s.colunas[0].obrigatoria is True


def test_from_dict_keeps_optional_fields():
    s = SheetSchema.from_dict(
        {
            "aba": "G",
            "colunas": [
                {
                    "nome": "Hora",
                    "campo": "hora",
                    "tipo": "hora",
                    "formato": "%H:%M",
                    "obrigatoria": False,
                }
            ],
        }
    )
    assert s.colunas[0].formato == "%H:%M"
    assert s.colunas[0].obrigatoria is False


@pytest.mark.parametrize(
    "data",
    [
        _data(aba=""),
        _data(aba="   "),
        {"colunas": _data()["colunas"]},
        _data(colunas=[]),
    ],
)
def test_from_dict_rejects_invalid_top_level(data):
    with pytest.raises(SchemaError):
        SheetSchema.from_dict(data)


def _coluna_valida():
    return {"nome": "ID", "campo": "id", "tipo": "texto"}


@pytest.mark.parametrize(
    ("coluna", "trecho"),
    [
        ({"nome": "Data", "tipo": "data"}, "Data"),
        ({"nome": "X", "campo": "data"}, "X"),
        ({"campo": "data", "tipo": "data"}, "nome"),
        ({"nome": "X", "campo": "inexistente", "tipo": "texto"}, "X"),
        ({"nome": "X", "campo": "data", "tipo": "cor"}, "X"),
    ],
)
def test_from_dict_column_errors_mention_column(coluna, trecho):
    with pytest.raises(SchemaError, match=trecho):
        SheetSchema.from_dict({"aba": "G", "colunas": [_coluna_valida(), coluna]})


def test_from_dict_rejects_duplicate_name():
    colunas = [
        {"nome": "Data", "campo": "data", "tipo": "data"},
        {"nome": "Data", "campo": "hora", "tipo": "hora"},
    ]
    with pytest.raises(SchemaError, match="Data"):
        SheetSchema.from_dict({"aba": "G", "colunas": colunas})


def test_from_dict_rejects_non_dict_columns():
    with pytest.raises(SchemaError):
        SheetSchema.from_dict({"aba": "G", "colunas": ["Data"]})


def test_load_reads_yaml_and_validates(tmp_path):
    path = tmp_path / "planilha.yaml"
    path.write_text(
        "aba: Gastos\ncolunas:\n  - nome: Data\n    campo: data\n    tipo: data\n",
        encoding="utf-8",
    )
    s = SheetSchema.load(path)
    assert s.aba == "Gastos"
    assert s.colunas[0].campo == "data"


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(SchemaError):
        SheetSchema.load(tmp_path / "nao-existe.yaml")


def test_load_invalid_yaml_raises(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("aba: [sem fechar\n", encoding="utf-8")
    with pytest.raises(SchemaError):
        SheetSchema.load(path)


def test_load_non_mapping_yaml_raises(tmp_path):
    path = tmp_path / "lista.yaml"
    path.write_text("- um\n- dois\n", encoding="utf-8")
    with pytest.raises(SchemaError):
        SheetSchema.load(path)
