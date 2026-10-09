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
from app.payment import calcular_parcelas
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


def _no_periodo(registros: list[Registro], inicio: date, fim: date) -> list[Registro]:
    """Registros com `inicio <= data <= fim` (período inclusivo)."""
    return [reg for reg in registros if inicio <= reg.data <= fim]


def _somar_por_moeda(registros: list[Registro]) -> Totais:
    """Soma os valores por moeda."""
    totais: Totais = {}
    for reg in registros:
        totais[reg.moeda] = totais.get(reg.moeda, Decimal("0")) + reg.valor_compra
    return totais


def _agrupar_por(registros: list[Registro], campo: str) -> dict[str, Totais]:
    """Agrupa os registros pelo valor de `campo`, somando por moeda em cada grupo."""
    grupos: dict[str, Totais] = {}
    for reg in registros:
        chave = getattr(reg, campo)
        totais = grupos.setdefault(chave, {})
        totais[reg.moeda] = totais.get(reg.moeda, Decimal("0")) + reg.valor_compra
    return grupos


def total_periodo(registros: list[Registro], inicio: date, fim: date) -> Totais:
    """Total gasto no período (inclusivo), por moeda."""
    return _somar_por_moeda(_no_periodo(registros, inicio, fim))


def total_por_categoria(registros: list[Registro], inicio: date, fim: date) -> dict[str, Totais]:
    """Total por categoria e moeda no período (inclusivo)."""
    return _agrupar_por(_no_periodo(registros, inicio, fim), "categoria")


def total_por_metodo(registros: list[Registro], inicio: date, fim: date) -> dict[str, Totais]:
    """Total por forma de pagamento e moeda no período (inclusivo)."""
    return _agrupar_por(_no_periodo(registros, inicio, fim), "metodo_pagamento")


def ultimos(registros: list[Registro], n: int) -> list[Registro]:
    """Os `n` registros mais recentes; empate de data mantém a ordem inversa da planilha."""
    ordenados = sorted(enumerate(registros), key=lambda par: (par[1].data, par[0]), reverse=True)
    return [reg for _, reg in ordenados[: max(n, 0)]]


def parcelas_futuras(registros: list[Registro], referencia: date) -> dict[str, Totais]:
    """Parcelas de compras parceladas com vencimento no mês de `referencia` ou depois.

    A parcela *k* (1..n) de uma compra vence no mês da compra + *k*. Retorna
    `{"AAAA-MM": {moeda: total}}` em ordem cronológica.
    """
    ref_index = referencia.year * 12 + (referencia.month - 1)
    totais: dict[str, Totais] = {}
    for reg in registros:
        if reg.metodo_pagamento != "credito_parcelado" or reg.quant_parcelas < 2:
            continue
        parcelas = calcular_parcelas(reg.valor_compra, reg.quant_parcelas)
        compra_index = reg.data.year * 12 + (reg.data.month - 1)
        for k, valor in enumerate(parcelas, start=1):
            idx = compra_index + k
            if idx < ref_index:
                continue
            ano, mes = divmod(idx, 12)
            chave = f"{ano:04d}-{mes + 1:02d}"
            por_moeda = totais.setdefault(chave, {})
            por_moeda[reg.moeda] = por_moeda.get(reg.moeda, Decimal("0")) + valor
    return dict(sorted(totais.items()))


class GastosRepository:
    """Lê as linhas da aba (com cache curto) e as converte em `Registro`."""

    def __init__(
        self,
        worksheet: Any,
        schema: SheetSchema,
        ttl_seconds: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._worksheet = worksheet
        self._schema = schema
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._cache: list[Registro] | None = None
        self._cache_at = 0.0

    def _carregar(self) -> list[Registro]:
        """Lê a planilha e converte as linhas (descarta o cabeçalho)."""
        try:
            rows = self._worksheet.get_all_values(
                value_render_option="UNFORMATTED_VALUE",
                date_time_render_option="FORMATTED_STRING",
            )
        except Exception as exc:  # qualquer falha do worksheet vira ReadError
            raise ReadError(f"falha ao ler a planilha: {exc}") from exc
        return parse_rows(self._schema, [list(row) for row in rows[1:]])

    def registros(self) -> list[Registro]:
        """Registros da planilha, em cache por `ttl_seconds` (relógio injetável)."""
        agora = self._clock()
        if self._cache is not None and (agora - self._cache_at) < self._ttl_seconds:
            return self._cache
        self._cache = self._carregar()
        self._cache_at = agora
        return self._cache

    def invalidate(self) -> None:
        """Descarta o cache, forçando nova leitura na próxima chamada."""
        self._cache = None
