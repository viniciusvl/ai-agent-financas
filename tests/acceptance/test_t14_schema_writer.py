import functools
from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import gspread
import pytest

from app.payment import Pagamento
from app.sheet_schema import SheetSchema
from app.sheets import PagamentoSheetWriter, SheetsError

pytestmark = pytest.mark.task("T14")

REG = datetime(2026, 10, 9, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
SCHEMA_DICT = {
    "aba": "Gastos",
    "colunas": [
        {"nome": "Data", "campo": "data", "tipo": "data"},
        {"nome": "ID", "campo": "id", "tipo": "texto"},
        {"nome": "Descrição", "campo": "descricao", "tipo": "texto"},
        {"nome": "Parcelas", "campo": "quant_parcelas", "tipo": "inteiro"},
        {"nome": "Valor", "campo": "valor_compra", "tipo": "moeda"},
        {"nome": "Parcela", "campo": "valor_parcela", "tipo": "moeda"},
        {"nome": "Usuário", "campo": "usuario", "tipo": "texto"},
    ],
}


@functools.cache
def _schema():
    return SheetSchema.from_dict(SCHEMA_DICT)


class FakeWorksheet:
    def __init__(self, rows=None, fail=False):
        self.rows = [list(r) for r in (rows or [])]
        self.fail = fail
        self.appended, self.col_reads, self.row_reads = [], [], 0

    def _check(self):
        if self.fail:
            raise RuntimeError("API down")

    def row_values(self, index):
        self._check()
        self.row_reads += 1
        return list(self.rows[index - 1]) if len(self.rows) >= index else []

    def col_values(self, col):
        self._check()
        self.col_reads.append(col)
        return [r[col - 1] if len(r) >= col else "" for r in self.rows]

    def insert_row(self, values, index=1, value_input_option="RAW"):
        self._check()
        self.rows.insert(index - 1, list(values))

    def append_row(self, values, value_input_option="RAW", **kwargs):
        self._check()
        self.appended.append({"values": list(values), "option": value_input_option})
        self.rows.append(list(values))


def pagamento(**kw):
    data = dict(
        metodo_pagamento="credito_parcelado",
        quant_parcelas=3,
        data=date(2026, 10, 9),
        hora=time(9, 0),
        valor_compra=Decimal("100"),
        descricao="tênis",
    )
    data.update(kw)
    return Pagamento(**data)


def test_requires_id_column():
    schema = SheetSchema.from_dict(
        {"aba": "G", "colunas": [{"nome": "Data", "campo": "data", "tipo": "data"}]}
    )
    with pytest.raises(SheetsError):
        PagamentoSheetWriter(FakeWorksheet(), schema)


def test_writes_header_and_row_in_schema_format():
    ws = FakeWorksheet()
    writer = PagamentoSheetWriter(ws, _schema())
    assert writer.append_pagamento(pagamento(), "Vini", REG, "abc") is True
    expected = _schema().to_row(pagamento(), {"id": "abc", "usuario": "Vini", "registrado_em": REG})
    assert ws.rows == [_schema().header(), expected]
    assert ws.appended == [{"values": expected, "option": "USER_ENTERED"}]
    assert expected[5] == 33.33


def test_existing_valid_header_is_kept():
    ws = FakeWorksheet(rows=[_schema().header()])
    PagamentoSheetWriter(ws, _schema()).append_pagamento(pagamento(), "Vini", REG, "abc")
    assert ws.rows[0] == _schema().header() and len(ws.rows) == 2


def test_divergent_header_blocks_writes():
    ws = FakeWorksheet(rows=[["Data", "Outra coisa"]])
    with pytest.raises(SheetsError, match="ID"):
        PagamentoSheetWriter(ws, _schema()).append_pagamento(pagamento(), "Vini", REG, "abc")
    assert ws.appended == []


def test_idempotent_by_id_within_instance():
    ws = FakeWorksheet()
    writer = PagamentoSheetWriter(ws, _schema())
    assert writer.append_pagamento(pagamento(), "Vini", REG, "abc") is True
    assert writer.append_pagamento(pagamento(), "Vini", REG, "abc") is False
    assert writer.append_pagamento(pagamento(), "Vini", REG, "def") is True
    assert len(ws.appended) == 2


def test_idempotent_against_existing_rows_and_reads_once():
    existing = _schema().to_row(
        pagamento(), {"id": "old1", "usuario": "Vini", "registrado_em": REG}
    )
    ws = FakeWorksheet(rows=[_schema().header(), existing])
    writer = PagamentoSheetWriter(ws, _schema())
    assert writer.append_pagamento(pagamento(), "Vini", REG, "old1") is False
    assert writer.append_pagamento(pagamento(), "Vini", REG, "new1") is True
    assert writer.append_pagamento(pagamento(), "Vini", REG, "new2") is True
    assert ws.col_reads == [2]
    assert ws.row_reads == 1


def test_formula_like_cells_are_escaped():
    ws = FakeWorksheet()
    writer = PagamentoSheetWriter(ws, _schema())
    writer.append_pagamento(pagamento(descricao="=1+1"), "@vini", REG, "-x1")
    row = ws.appended[0]["values"]
    assert row[1] == "'-x1"
    assert row[2] == "'=1+1"
    assert row[6] == "'@vini"
    assert row[4] == 100.0


def test_errors_are_wrapped():
    with pytest.raises(SheetsError):
        PagamentoSheetWriter(FakeWorksheet(fail=True), _schema()).append_pagamento(
            pagamento(), "Vini", REG, "abc"
        )


def test_from_service_account(monkeypatch):
    ws = FakeWorksheet()
    calls = {}

    class Spreadsheet:
        def worksheet(self, name):
            calls["aba"] = name
            return ws

    def service_account(filename):
        calls["file"] = filename
        return SimpleNamespace(open_by_key=lambda key: calls.update(key=key) or Spreadsheet())

    monkeypatch.setattr(gspread, "service_account", service_account)
    writer = PagamentoSheetWriter.from_service_account("creds.json", "SHEET", _schema())
    assert writer.worksheet is ws
    assert calls == {"file": "creds.json", "key": "SHEET", "aba": "Gastos"}


def test_from_service_account_creates_tab(monkeypatch):
    created, adds = FakeWorksheet(), []

    class Spreadsheet:
        def worksheet(self, name):
            raise gspread.exceptions.WorksheetNotFound(name)

        def add_worksheet(self, title, rows, cols):
            adds.append((title, rows, cols))
            return created

    monkeypatch.setattr(
        gspread,
        "service_account",
        lambda filename: SimpleNamespace(open_by_key=lambda k: Spreadsheet()),
    )
    writer = PagamentoSheetWriter.from_service_account("creds.json", "SHEET", _schema())
    assert writer.worksheet is created
    assert adds == [("Gastos", 1000, len(_schema().colunas))]


def test_from_service_account_errors(monkeypatch):
    def boom(filename):
        raise FileNotFoundError(filename)

    monkeypatch.setattr(gspread, "service_account", boom)
    with pytest.raises(SheetsError):
        PagamentoSheetWriter.from_service_account("nao-existe.json", "SHEET", _schema())
