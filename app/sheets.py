"""Persistência dos gastos no Google Sheets (gspread + service account).

Spec: specs/tasks/T06-google-sheets.md
"""

from datetime import datetime
from typing import Any

import gspread

from app.domain import SHEET_HEADER, Expense, to_sheet_row
from app.sheet_schema import SchemaError


class SheetsError(Exception):
    """Falha ao ler/escrever na planilha."""


_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _escape_formula_cells(row: list[Any]) -> list[Any]:
    """Prefixa com `'` células de texto que o Sheets interpretaria como fórmula.

    Com `USER_ENTERED`, textos iniciados por `=`, `+`, `-` ou `@` viram fórmulas;
    o prefixo força a leitura como texto. Números e demais strings ficam intactos.
    """
    escaped: list[Any] = []
    for cell in row:
        if isinstance(cell, str) and cell.startswith(_FORMULA_PREFIXES):
            escaped.append("'" + cell)
        else:
            escaped.append(cell)
    return escaped


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
        row = _escape_formula_cells(row)
        try:
            self.worksheet.append_row(row, value_input_option="USER_ENTERED")
        except SheetsError:
            raise
        except Exception as exc:
            raise SheetsError("falha ao gravar o gasto na planilha") from exc


class PagamentoSheetWriter:
    """Grava `Pagamento` (v2) no formato do schema da planilha, sem duplicar ids.

    Spec: specs/tasks/T14-schema-writer.md
    """

    def __init__(self, worksheet: Any, schema: Any) -> None:
        # A idempotência por `id_gasto` depende de uma coluna com `campo: id`.
        if not any(coluna.campo == "id" for coluna in schema.colunas):
            raise SheetsError("schema sem coluna com campo 'id' (necessária para a idempotência)")
        self.worksheet = worksheet
        self.schema = schema
        # Memoriza o sucesso de `ensure_header` para ler o cabeçalho apenas uma vez.
        self._header_ready = False
        # Ids já vistos nesta instância (carregados da planilha + gravados aqui).
        self._ids_loaded = False
        self._known_ids: set[str] = set()

    @classmethod
    def from_service_account(
        cls, service_account_file: str, sheet_id: str, schema: Any
    ) -> "PagamentoSheetWriter":
        """Conecta via service account e devolve o escritor da aba do schema.

        Cria a aba se ela ainda não existir.
        """
        try:
            client = gspread.service_account(filename=service_account_file)
            spreadsheet = client.open_by_key(sheet_id)
            try:
                worksheet = spreadsheet.worksheet(schema.aba)
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title=schema.aba, rows=1000, cols=len(schema.colunas)
                )
        except SheetsError:
            raise
        except Exception as exc:
            raise SheetsError("falha ao conectar à planilha") from exc
        return cls(worksheet, schema)

    def ensure_header(self) -> None:
        """Garante que a primeira linha seja o cabeçalho do schema.

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
                self.worksheet.insert_row(self.schema.header(), index=1)
            except SheetsError:
                raise
            except Exception as exc:
                raise SheetsError("falha ao criar o cabeçalho da planilha") from exc
            return

        try:
            self.schema.validate_header(current)
        except SchemaError as exc:
            raise SheetsError(str(exc)) from exc

    def _load_existing_ids(self) -> set[str]:
        """Lê os ids já presentes na planilha, ignorando o cabeçalho."""
        # Descobre a posição 1-based da coluna id (garantida no __init__).
        posicao = 0
        for i, coluna in enumerate(self.schema.colunas):
            if coluna.campo == "id":
                posicao = i + 1
                break
        try:
            valores = self.worksheet.col_values(posicao)
        except SheetsError:
            raise
        except Exception as exc:
            raise SheetsError("falha ao ler os ids existentes na planilha") from exc
        return {str(valor) for valor in valores[1:] if valor not in (None, "")}

    def append_pagamento(
        self, pagamento: Any, usuario: str, registrado_em: datetime, id_gasto: str
    ) -> bool:
        """Anexa o pagamento na planilha, garantindo o cabeçalho antes.

        Idempotente por `id_gasto`: ids já conhecidos (da planilha ou gravados
        nesta instância) não são reinseridos e a função retorna `False`.
        """
        if not self._ids_loaded:
            if not self._header_ready:
                self.ensure_header()
                self._header_ready = True
            self._known_ids = self._load_existing_ids()
            self._ids_loaded = True

        if id_gasto in self._known_ids:
            return False

        try:
            linha = self.schema.to_row(
                pagamento,
                {"id": id_gasto, "usuario": usuario, "registrado_em": registrado_em},
            )
        except SchemaError as exc:
            raise SheetsError(str(exc)) from exc

        linha = _escape_formula_cells(linha)
        try:
            self.worksheet.append_row(linha, value_input_option="USER_ENTERED")
        except SheetsError:
            raise
        except Exception as exc:
            raise SheetsError("falha ao gravar o pagamento na planilha") from exc
        self._known_ids.add(id_gasto)
        return True
