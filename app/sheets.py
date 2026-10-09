"""Persistência dos gastos no Google Sheets (gspread + service account).

Spec: specs/tasks/T06-google-sheets.md
"""

from datetime import datetime
from typing import Any

import gspread

from app.domain import SHEET_HEADER, Expense, to_sheet_row


class SheetsError(Exception):
    """Falha ao ler/escrever na planilha."""


class SheetsRepository:
    def __init__(self, worksheet: Any) -> None:
        # `worksheet` é um gspread.Worksheet (ou fake com a mesma interface nos testes).
        self.worksheet = worksheet
        # Memoriza o sucesso de `ensure_header` para ler o cabeçalho apenas uma vez.
        self._header_ready = False

    @classmethod
    def from_service_account(
        cls, service_account_file: str, sheet_id: str, worksheet_name: str
    ) -> "SheetsRepository":
        """Conecta via service account e devolve o repositório da aba indicada.

        Cria a aba se ela ainda não existir.
        """
        try:
            client = gspread.service_account(filename=service_account_file)
            spreadsheet = client.open_by_key(sheet_id)
            try:
                worksheet = spreadsheet.worksheet(worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title=worksheet_name, rows=1000, cols=len(SHEET_HEADER)
                )
        except SheetsError:
            raise
        except Exception as exc:
            raise SheetsError("falha ao conectar à planilha") from exc
        return cls(worksheet)

    def ensure_header(self) -> None:
        """Garante que a primeira linha seja o cabeçalho esperado.

        Aba vazia recebe o cabeçalho; cabeçalho divergente levanta `SheetsError`.
        """
        try:
            current = self.worksheet.row_values(1)
        except SheetsError:
            raise
        except Exception as exc:
            raise SheetsError("falha ao ler o cabeçalho da planilha") from exc

        if not current:
            try:
                self.worksheet.insert_row(SHEET_HEADER, index=1)
            except SheetsError:
                raise
            except Exception as exc:
                raise SheetsError("falha ao criar o cabeçalho da planilha") from exc
            return

        if current != SHEET_HEADER:
            raise SheetsError("cabeçalho da planilha não corresponde ao esperado")

    def append_expense(self, expense: Expense, user: str, recorded_at: datetime) -> None:
        """Anexa o gasto confirmado à planilha, garantindo o cabeçalho antes."""
        if not self._header_ready:
            self.ensure_header()
            self._header_ready = True

        row = to_sheet_row(expense, user, recorded_at)
        try:
            self.worksheet.append_row(row, value_input_option="USER_ENTERED")
        except SheetsError:
            raise
        except Exception as exc:
            raise SheetsError("falha ao gravar o gasto na planilha") from exc
