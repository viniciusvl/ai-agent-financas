"""Testes de concorrência do `PagamentoSheetWriter` (T14).

Cobre a condição de corrida do duplo clique: o bot chama `append_pagamento`
via `asyncio.to_thread`, então dois callbacks podem correr em paralelo. Sem o
lock da instância, os dois passariam pela verificação de id e gravariam linhas
duplicadas.
"""

import threading
import time
from datetime import date, datetime
from datetime import time as time_cls
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.payment import Pagamento
from app.sheet_schema import SheetSchema
from app.sheets import PagamentoSheetWriter

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


def _schema() -> SheetSchema:
    return SheetSchema.from_dict(SCHEMA_DICT)


def _pagamento() -> Pagamento:
    return Pagamento(
        metodo_pagamento="credito_parcelado",
        quant_parcelas=3,
        data=date(2026, 10, 9),
        hora=time_cls(9, 0),
        valor_compra=Decimal("100"),
        descricao="tênis",
    )


class SlowFakeWorksheet:
    """Worksheet fake cujo `append_row` demora ~50 ms para expor a corrida."""

    def __init__(self) -> None:
        self._rows: list[list] = []
        self._counters_lock = threading.Lock()
        self.appended: list[list] = []
        self.col_reads = 0
        self.row_reads = 0

    def row_values(self, index: int) -> list:
        with self._counters_lock:
            self.row_reads += 1
        return list(self._rows[index - 1]) if len(self._rows) >= index else []

    def col_values(self, col: int) -> list:
        with self._counters_lock:
            self.col_reads += 1
        return [r[col - 1] if len(r) >= col else "" for r in self._rows]

    def insert_row(self, values, index: int = 1, value_input_option: str = "RAW") -> None:
        self._rows.insert(index - 1, list(values))

    def append_row(self, values, value_input_option: str = "RAW", **kwargs) -> None:
        time.sleep(0.05)
        with self._counters_lock:
            self.appended.append(list(values))
        self._rows.append(list(values))


def test_concurrent_same_id_appends_once():
    ws = SlowFakeWorksheet()
    writer = PagamentoSheetWriter(ws, _schema())
    results: list[bool] = []
    results_lock = threading.Lock()

    def worker() -> None:
        result = writer.append_pagamento(_pagamento(), "Vini", REG, "same-id")
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(ws.appended) == 1
    assert results.count(True) == 1
    assert results.count(False) == 9
    assert ws.col_reads == 1
