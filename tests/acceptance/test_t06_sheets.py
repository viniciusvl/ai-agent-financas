from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import gspread
import pytest

from app.domain import SHEET_HEADER, Expense, to_sheet_row
from app.sheets import SheetsError, SheetsRepository

pytestmark = pytest.mark.task("T06")

RECORDED_AT = datetime(2026, 10, 8, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


class FakeWorksheet:
    def __init__(self, rows=None, fail=False):
        self.rows = [list(r) for r in (rows or [])]
        self.fail = fail
        self.append_calls = []
        self.read_calls = 0

    def _check(self):
        if self.fail:
            raise RuntimeError("API down")

    def row_values(self, index):
        self._check()
        self.read_calls += 1
        return list(self.rows[index - 1]) if len(self.rows) >= index else []

    def insert_row(self, values, index=1, value_input_option="RAW"):
        self._check()
        self.rows.insert(index - 1, list(values))

    def append_row(self, values, value_input_option="RAW", **kwargs):
        self._check()
        self.append_calls.append({"values": list(values), "value_input_option": value_input_option})
        self.rows.append(list(values))


def expense():
    return Expense(
        amount=Decimal("80"),
        description="táxi",
        category="transporte",
        spent_at=date(2026, 10, 8),
        raw_text="táxi 80",
    )


def test_ensure_header_on_empty_sheet():
    ws = FakeWorksheet()
    SheetsRepository(ws).ensure_header()
    assert ws.rows == [SHEET_HEADER]


def test_ensure_header_when_present_is_noop():
    ws = FakeWorksheet(rows=[SHEET_HEADER, ["x"]])
    SheetsRepository(ws).ensure_header()
    assert ws.rows == [SHEET_HEADER, ["x"]]


def test_ensure_header_with_unexpected_first_row_raises():
    ws = FakeWorksheet(rows=[["Outra", "coisa"]])
    with pytest.raises(SheetsError):
        SheetsRepository(ws).ensure_header()


def test_append_expense_on_empty_sheet_writes_header_then_row():
    ws = FakeWorksheet()
    SheetsRepository(ws).append_expense(expense(), "Vini", RECORDED_AT)
    expected_row = to_sheet_row(expense(), "Vini", RECORDED_AT)
    assert ws.rows == [SHEET_HEADER, expected_row]
    assert ws.append_calls == [{"values": expected_row, "value_input_option": "USER_ENTERED"}]


def test_header_is_checked_only_once():
    ws = FakeWorksheet()
    repo = SheetsRepository(ws)
    for _ in range(3):
        repo.append_expense(expense(), "Vini", RECORDED_AT)
    assert ws.read_calls == 1
    assert len(ws.rows) == 4


def test_errors_are_wrapped():
    repo = SheetsRepository(FakeWorksheet(fail=True))
    with pytest.raises(SheetsError):
        repo.append_expense(expense(), "Vini", RECORDED_AT)


def test_from_service_account_existing_worksheet(monkeypatch):
    ws = FakeWorksheet()
    calls = {}

    class FakeSpreadsheet:
        def worksheet(self, name):
            calls["worksheet"] = name
            return ws

        def add_worksheet(self, **kwargs):  # pragma: no cover - não deve ser chamado
            raise AssertionError("não deveria criar")

    def fake_service_account(filename):
        calls["filename"] = filename
        return SimpleNamespace(open_by_key=lambda key: calls.update(key=key) or FakeSpreadsheet())

    monkeypatch.setattr(gspread, "service_account", fake_service_account)
    repo = SheetsRepository.from_service_account("creds.json", "SHEET123", "Gastos")
    assert repo.worksheet is ws
    assert calls == {"filename": "creds.json", "key": "SHEET123", "worksheet": "Gastos"}


def test_from_service_account_creates_missing_worksheet(monkeypatch):
    created = FakeWorksheet()
    add_calls = []

    class FakeSpreadsheet:
        def worksheet(self, name):
            raise gspread.exceptions.WorksheetNotFound(name)

        def add_worksheet(self, title, rows, cols):
            add_calls.append((title, rows, cols))
            return created

    monkeypatch.setattr(
        gspread,
        "service_account",
        lambda filename: SimpleNamespace(open_by_key=lambda key: FakeSpreadsheet()),
    )
    repo = SheetsRepository.from_service_account("creds.json", "SHEET123", "Gastos")
    assert repo.worksheet is created
    assert add_calls == [("Gastos", 1000, len(SHEET_HEADER))]
