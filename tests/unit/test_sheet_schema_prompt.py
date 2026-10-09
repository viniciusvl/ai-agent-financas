"""Testes unitários de `prompt_context`/`validate_header` (spec T11, subtarefa 3)."""

import pytest

from app.sheet_schema import SchemaError, SheetSchema


def _schema(**changes):
    data = {
        "aba": "Gastos",
        "colunas": [
            {"nome": "ID", "campo": "id", "tipo": "texto"},
            {"nome": "Data", "campo": "data", "tipo": "data", "formato": "%Y-%m-%d"},
            {"nome": "Valor", "campo": "valor_compra", "tipo": "moeda"},
        ],
    }
    data.update(changes)
    return SheetSchema.from_dict(data)


def test_prompt_context_lists_aba_and_columns():
    texto = _schema().prompt_context()
    linhas = texto.splitlines()
    assert linhas[0] == "Colunas da planilha (aba Gastos):"
    assert "- ID: campo id, tipo texto" in linhas
    assert "- Data: campo data, tipo data, formato %Y-%m-%d" in linhas
    assert "- Valor: campo valor_compra, tipo moeda" in linhas


def test_prompt_context_omits_format_when_absent():
    texto = _schema().prompt_context()
    assert "- ID: campo id, tipo texto, formato" not in texto


def test_validate_header_accepts_exact_header():
    s = _schema()
    s.validate_header(s.header())


def test_validate_header_points_to_first_divergence():
    s = _schema()
    header = s.header()
    swapped = header[:]
    swapped[0], swapped[1] = swapped[1], swapped[0]
    with pytest.raises(SchemaError) as exc:
        s.validate_header(swapped)
    assert "1" in str(exc.value)
    assert "ID" in str(exc.value)


def test_validate_header_rejects_shorter_and_longer():
    s = _schema()
    header = s.header()
    with pytest.raises(SchemaError):
        s.validate_header(header[:-1])
    with pytest.raises(SchemaError):
        s.validate_header([*header, "Extra"])
