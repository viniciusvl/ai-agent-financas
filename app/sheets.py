"""Persistência dos gastos no Google Sheets (gspread + service account).

Spec: specs/tasks/T06-google-sheets.md
"""

import logging
from datetime import datetime
from typing import Any

import gspread

from app.domain import SHEET_HEADER, Expense, to_sheet_row

logger = logging.getLogger(__name__)

# Número de linhas criadas ao adicionar uma aba nova.
_WORKSHEET_ROWS = 1000


class SheetsError(Exception):
    """Falha ao ler/escrever na planilha."""


class SheetsRepository:
    def __init__(self, worksheet: Any) -> None:
        # `worksheet` é um gspread.Worksheet (ou fake com a mesma interface nos testes).
        self.worksheet = worksheet
        # Só verifica/cria o cabeçalho na primeira gravação da instância.
        self._header_ready = False

    @classmethod
    def from_service_account(
        cls, service_account_file: str, sheet_id: str, worksheet_name: str
    ) -> "SheetsRepository":
        """Abre a planilha via service account, criando a aba se ela não existir."""
        try:
            client = gspread.service_account(filename=service_account_file)
            spreadsheet = client.open_by_key(sheet_id)
            try:
                worksheet = spreadsheet.worksheet(worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                logger.info("Aba %r não existe; criando.", worksheet_name)
                worksheet = spreadsheet.add_worksheet(
                    title=worksheet_name,
                    rows=_WORKSHEET_ROWS,
                    cols=len(SHEET_HEADER),
                )
        except SheetsError:
            raise
        except Exception as exc:
            raise SheetsError(f"falha ao abrir a planilha {sheet_id!r}") from exc
        return cls(worksheet)

    def ensure_header(self) -> None:
        """Garante que a primeira linha é o cabeçalho esperado."""
        try:
            first_row = self.worksheet.row_values(1)
            if not first_row:
                self.worksheet.insert_row(SHEET_HEADER, index=1)
            elif first_row != SHEET_HEADER:
                raise SheetsError("cabeçalho inesperado na planilha")
        except SheetsError:
            raise
        except Exception as exc:
            raise SheetsError("falha ao garantir o cabeçalho da planilha") from exc

    def append_expense(self, expense: Expense, user: str, recorded_at: datetime) -> None:
        """Grava o gasto confirmado; verifica o cabeçalho apenas na primeira vez."""
        try:
            if not self._header_ready:
                self.ensure_header()
                self._header_ready = True
            self.worksheet.append_row(
                to_sheet_row(expense, user, recorded_at),
                value_input_option="USER_ENTERED",
            )
        except SheetsError:
            raise
        except Exception as exc:
            raise SheetsError("falha ao gravar o gasto na planilha") from exc
