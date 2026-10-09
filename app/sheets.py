"""Persistência dos gastos no Google Sheets (gspread + service account).

Spec: specs/tasks/T06-google-sheets.md
"""

from datetime import datetime
from typing import Any

from app.domain import Expense


class SheetsError(Exception):
    """Falha ao ler/escrever na planilha."""


class SheetsRepository:
    def __init__(self, worksheet: Any) -> None:
        # `worksheet` é um gspread.Worksheet (ou fake com a mesma interface nos testes).
        self.worksheet = worksheet

    @classmethod
    def from_service_account(
        cls, service_account_file: str, sheet_id: str, worksheet_name: str
    ) -> "SheetsRepository":
        raise NotImplementedError("T06")

    def ensure_header(self) -> None:
        raise NotImplementedError("T06")

    def append_expense(self, expense: Expense, user: str, recorded_at: datetime) -> None:
        raise NotImplementedError("T06")
