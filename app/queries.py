"""Consultas determinísticas sobre os gastos gravados na planilha (sem LLM).

Spec: specs/tasks/T15-read-path.md
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.sheet_schema import SheetSchema

Totais = dict[str, Decimal]  # moeda → total


class ReadError(Exception):
    """Falha ao consultar o LLM ou a planilha."""


@dataclass(frozen=True)
class Registro:
    data: date
    valor_compra: Decimal
    moeda: str = "CNY"
    categoria: str = "outros"
    metodo_pagamento: str = "outro"
    quant_parcelas: int = 1
    descricao: str = ""


def format_valor(moeda: str, valor: Decimal) -> str:
    """CNY → "¥ 1.234,56"; BRL → "R$ 1.234,56"; USD → "US$ 1.234,56"; outras → "XXX 1.234,56"."""
    raise NotImplementedError("T15")


def format_totais(totais: Totais) -> str:
    raise NotImplementedError("T15")


def parse_rows(schema: SheetSchema, rows: list[list[Any]]) -> list[Registro]:
    raise NotImplementedError("T15")


def total_periodo(registros: list[Registro], inicio: date, fim: date) -> Totais:
    raise NotImplementedError("T15")


def total_por_categoria(registros: list[Registro], inicio: date, fim: date) -> dict[str, Totais]:
    raise NotImplementedError("T15")


def total_por_metodo(registros: list[Registro], inicio: date, fim: date) -> dict[str, Totais]:
    raise NotImplementedError("T15")


def ultimos(registros: list[Registro], n: int) -> list[Registro]:
    raise NotImplementedError("T15")


def parcelas_futuras(registros: list[Registro], referencia: date) -> dict[str, Totais]:
    raise NotImplementedError("T15")


class GastosRepository:
    """Lê as linhas da aba (com cache curto) e as converte em `Registro`."""

    def __init__(
        self,
        worksheet: Any,
        schema: SheetSchema,
        ttl_seconds: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        raise NotImplementedError("T15")

    def registros(self) -> list[Registro]:
        raise NotImplementedError("T15")

    def invalidate(self) -> None:
        raise NotImplementedError("T15")
