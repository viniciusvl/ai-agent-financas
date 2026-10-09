"""Consultas determinísticas sobre os gastos gravados na planilha (sem LLM).

Spec: specs/tasks/T15-read-path.md
"""

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.messages import MSG_NENHUM_GASTO
from app.sheet_schema import SheetSchema

logger = logging.getLogger(__name__)

Totais = dict[str, Decimal]  # moeda → total

_CENTAVOS = Decimal("0.01")

# Prefixos das moedas conhecidas; demais recebem "<MOEDA> ".
_PREFIXOS_MOEDA: dict[str, str] = {
    "CNY": "¥ ",
    "BRL": "R$ ",
    "USD": "US$ ",
}


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


def _parse_valor(valor: Any) -> Decimal:
    """Converte um valor bruto (número ou texto com símbolo de moeda) em `Decimal` > 0."""
    if isinstance(valor, bool):
        raise ValueError(f"valor inválido: {valor!r}")
    if isinstance(valor, Decimal):
        amount = valor
    elif isinstance(valor, int):
        amount = Decimal(valor)
    elif isinstance(valor, float):
        amount = Decimal(str(valor))
    elif isinstance(valor, str):
        texto = re.sub(r"[^\d,.\-]", "", valor)
        if not texto:
            raise ValueError(f"valor inválido: {valor!r}")
        if "," in texto:
            # Formato pt-BR: "." separa milhar e "," separa decimal.
            texto = texto.replace(".", "").replace(",", ".")
        try:
            amount = Decimal(texto)
        except InvalidOperation as exc:
            raise ValueError(f"valor inválido: {valor!r}") from exc
    else:
        raise ValueError(f"valor inválido: {valor!r}")

    if not amount.is_finite():
        raise ValueError(f"valor inválido: {valor!r}")
    amount = amount.quantize(_CENTAVOS, rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise ValueError(f"valor deve ser maior que zero: {valor!r}")
    return amount


def _parse_data(valor: Any, formato: str | None) -> date:
    """Converte a célula de data; aceita `date`/`datetime` e strings em formatos conhecidos."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        texto = valor.strip()
        if texto:
            for fmt in (formato, "%Y-%m-%d", "%d/%m/%Y"):
                if not fmt:
                    continue
                try:
                    return datetime.strptime(texto, fmt).date()
                except ValueError:
                    continue
    raise ValueError(f"data inválida: {valor!r}")


def _parse_quant_parcelas(valor: Any) -> int:
    """Converte a quantidade de parcelas para inteiro; ausente/vazio vira 1."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return 1
    if isinstance(valor, bool):
        raise ValueError(f"quantidade de parcelas inválida: {valor!r}")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        if valor != int(valor):
            raise ValueError(f"quantidade de parcelas inválida: {valor!r}")
        return int(valor)
    if isinstance(valor, Decimal):
        if valor != valor.to_integral_value():
            raise ValueError(f"quantidade de parcelas inválida: {valor!r}")
        return int(valor)
    if isinstance(valor, str):
        try:
            numero = Decimal(valor.strip())
        except InvalidOperation as exc:
            raise ValueError(f"quantidade de parcelas inválida: {valor!r}") from exc
        if numero != numero.to_integral_value():
            raise ValueError(f"quantidade de parcelas inválida: {valor!r}")
        return int(numero)
    raise ValueError(f"quantidade de parcelas inválida: {valor!r}")


def _texto(valor: Any, padrao: str = "") -> str:
    """Converte uma célula em texto sem espaços nas pontas; vazio usa o padrão."""
    if valor is None:
        return padrao
    texto = str(valor).strip()
    return texto or padrao


def format_valor(moeda: str, valor: Decimal) -> str:
    """CNY → "¥ 1.234,56"; BRL → "R$ 1.234,56"; USD → "US$ 1.234,56"; outras → "XXX 1.234,56"."""
    numero = f"{valor:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{_PREFIXOS_MOEDA.get(moeda, f'{moeda} ')}{numero}"


def format_totais(totais: Totais) -> str:
    """Moedas em ordem alfabética, `format_valor` unidos por " + "; vazio → `MSG_NENHUM_GASTO`."""
    if not totais:
        return MSG_NENHUM_GASTO
    return " + ".join(format_valor(moeda, totais[moeda]) for moeda in sorted(totais))


def parse_rows(schema: SheetSchema, rows: list[list[Any]]) -> list[Registro]:
    """Converte as linhas (sem cabeçalho) em `Registro`, ignorando linhas inválidas."""
    colunas = {coluna.campo: coluna for coluna in schema.colunas}
    posicao = {coluna.campo: i for i, coluna in enumerate(schema.colunas)}

    def celula(row: list[Any], campo: str) -> Any:
        i = posicao.get(campo)
        if i is None or i >= len(row):
            return None
        return row[i]

    regs: list[Registro] = []
    for indice, row in enumerate(rows):
        numero = indice + 2  # +1 pela linha (0-based) e +1 pelo cabeçalho
        try:
            formato_data = colunas["data"].formato if "data" in colunas else None
            data = _parse_data(celula(row, "data"), formato_data)
            valor = _parse_valor(celula(row, "valor_compra"))
        except ValueError as exc:
            logger.warning("linha %d ignorada: %s", numero, exc)
            continue

        try:
            quant_parcelas = _parse_quant_parcelas(celula(row, "quant_parcelas"))
        except ValueError:
            quant_parcelas = 1

        regs.append(
            Registro(
                data=data,
                valor_compra=valor,
                moeda=_texto(celula(row, "moeda"), "CNY"),
                categoria=_texto(celula(row, "categoria"), "outros"),
                metodo_pagamento=_texto(celula(row, "metodo_pagamento"), "outro"),
                quant_parcelas=quant_parcelas,
                descricao=_texto(celula(row, "descricao")),
            )
        )
    return regs


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
