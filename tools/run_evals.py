"""Avaliação (evals) do roteador e do extrator de pagamentos.

Uso:
    python -m tools.run_evals --check   # valida evals/casos.yaml (formato + cobertura), sem rede
    python -m tools.run_evals --live    # chama as APIs reais e grava evals/resultados/AAAA-MM-DD.md

Spec: specs/tasks/T17-evals.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

CASOS_PATH = Path(__file__).resolve().parents[1] / "evals" / "casos.yaml"
CAMPOS_AVALIADOS = ("valor_compra", "moeda", "metodo_pagamento", "quant_parcelas", "categoria")
LIMIAR_ROTA = 0.95
LIMIAR_CAMPOS = 0.90


class CasosError(Exception):
    """Arquivo de casos inválido ou sem a cobertura mínima."""


@dataclass
class Caso:
    id: str
    texto: str
    rota: str
    esperado: dict[str, Any] = field(default_factory=dict)


@dataclass
class Relatorio:
    total: int
    acuracia_rota: float
    acuracia_campos: float
    acertos_por_campo: dict[str, float]
    latencia_media_ms: float
    falhas: list[str]


def load_casos(path: Path = CASOS_PATH) -> list[Caso]:
    raise NotImplementedError("T17")


def verificar_cobertura(casos: list[Caso]) -> None:
    raise NotImplementedError("T17")


async def avaliar(
    casos: list[Caso], router: Any, extractor: Any, recebido_em: datetime
) -> Relatorio:
    raise NotImplementedError("T17")


def render_relatorio(rel: Relatorio, quando: datetime) -> str:
    raise NotImplementedError("T17")


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError("T17")


if __name__ == "__main__":
    raise SystemExit(main())
