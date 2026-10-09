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

import yaml

CASOS_PATH = Path(__file__).resolve().parents[1] / "evals" / "casos.yaml"
CAMPOS_AVALIADOS = ("valor_compra", "moeda", "metodo_pagamento", "quant_parcelas", "categoria")
LIMIAR_ROTA = 0.95
LIMIAR_CAMPOS = 0.90
ROTAS = ("escrita", "leitura", "outro")


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


def _parse_caso(item: Any) -> Caso:
    """Valida um caso bruto do YAML e o converte em `Caso`.

    Erros trazem o `id` do caso (quando disponível) para facilitar a correção do arquivo.
    """
    if not isinstance(item, dict):
        raise CasosError(f"caso inválido (esperado mapeamento): {item!r}")

    caso_id = item.get("id")
    if not isinstance(caso_id, str) or not caso_id.strip():
        raise CasosError(f"caso sem 'id' válido: {item!r}")

    texto = item.get("texto")
    if not isinstance(texto, str) or not texto.strip():
        raise CasosError(f"{caso_id}: 'texto' não pode ser vazio")

    rota = item.get("rota")
    if rota not in ROTAS:
        raise CasosError(f"{caso_id}: rota inválida: {rota!r} (esperado {'/'.join(ROTAS)})")

    esperado = item.get("esperado")
    if esperado is None:
        esperado = {}
    if not isinstance(esperado, dict):
        raise CasosError(f"{caso_id}: 'esperado' deve ser um mapeamento")

    if esperado and rota != "escrita":
        raise CasosError(f"{caso_id}: 'esperado' só é permitido em casos de rota escrita")

    desconhecidos = sorted(set(esperado) - set(CAMPOS_AVALIADOS))
    if desconhecidos:
        raise CasosError(f"{caso_id}: campos não avaliados em 'esperado': {desconhecidos}")

    return Caso(id=caso_id, texto=texto, rota=rota, esperado=dict(esperado))


def load_casos(path: Path = CASOS_PATH) -> list[Caso]:
    """Lê e valida o arquivo de casos; `CasosError` descreve a primeira inconsistência."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CasosError(f"arquivo de casos não encontrado: {path}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("casos"), list):
        raise CasosError("YAML inválido: esperado um mapeamento com a chave 'casos' (lista)")

    casos: list[Caso] = []
    vistos: set[str] = set()
    for item in raw["casos"]:
        caso = _parse_caso(item)
        if caso.id in vistos:
            raise CasosError(f"id duplicado: {caso.id}")
        vistos.add(caso.id)
        casos.append(caso)
    return casos


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
