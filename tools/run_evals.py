"""Avaliação (evals) do roteador e do extrator de pagamentos.

Uso:
    python -m tools.run_evals --check   # valida evals/casos.yaml (formato + cobertura), sem rede
    python -m tools.run_evals --live    # chama as APIs reais e grava evals/resultados/AAAA-MM-DD.md

Spec: specs/tasks/T17-evals.md
"""

import argparse
from collections import Counter
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

# Cobertura mínima exigida de `evals/casos.yaml` (spec T17).
MIN_POR_ROTA = {"escrita": 30, "leitura": 15, "outro": 10}
METODOS_PAGAMENTO = (
    "dinheiro",
    "debito",
    "credito_a_vista",
    "credito_parcelado",
    "pix",
    "alipay",
    "wechat_pay",
    "outro",
)
MIN_POR_METODO = 2
MIN_POR_MOEDA = {"CNY": 10, "BRL": 5, "USD": 3}
MIN_PARCELADOS = 6
MIN_PARCELAS_DISTINTAS = 4


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
    """Garante a cobertura mínima do conjunto de casos (spec T17).

    Levanta `CasosError` descrevendo tudo o que falta; não altera o conjunto.
    """
    problemas: list[str] = []

    por_rota = Counter(c.rota for c in casos)
    for rota, minimo in MIN_POR_ROTA.items():
        if por_rota[rota] < minimo:
            problemas.append(f"rota '{rota}': {por_rota[rota]}/{minimo}")

    escritas = [c for c in casos if c.rota == "escrita"]
    sem_valor = [c.id for c in escritas if "valor_compra" not in c.esperado]
    if sem_valor:
        problemas.append(f"casos escrita sem 'valor_compra' esperado: {', '.join(sem_valor)}")

    por_metodo = Counter(c.esperado.get("metodo_pagamento") for c in escritas)
    for metodo in METODOS_PAGAMENTO:
        if por_metodo[metodo] < MIN_POR_METODO:
            problemas.append(f"metodo_pagamento '{metodo}': {por_metodo[metodo]}/{MIN_POR_METODO}")

    por_moeda = Counter(c.esperado.get("moeda") for c in casos)
    for moeda, minimo in MIN_POR_MOEDA.items():
        if por_moeda[moeda] < minimo:
            problemas.append(f"moeda '{moeda}': {por_moeda[moeda]}/{minimo}")

    parcelas = [
        c.esperado["quant_parcelas"]
        for c in casos
        if c.esperado.get("metodo_pagamento") == "credito_parcelado"
        and "quant_parcelas" in c.esperado
    ]
    if len(parcelas) < MIN_PARCELADOS:
        problemas.append(
            f"credito_parcelado com quant_parcelas: {len(parcelas)}/{MIN_PARCELADOS}",
        )
    distintas = len(set(parcelas))
    if distintas < MIN_PARCELAS_DISTINTAS:
        problemas.append(
            f"valores distintos de quant_parcelas: {distintas}/{MIN_PARCELAS_DISTINTAS}"
        )

    if problemas:
        raise CasosError("cobertura insuficiente: " + "; ".join(problemas))


async def avaliar(
    casos: list[Caso], router: Any, extractor: Any, recebido_em: datetime
) -> Relatorio:
    raise NotImplementedError("T17")


def render_relatorio(rel: Relatorio, quando: datetime) -> str:
    raise NotImplementedError("T17")


def main(argv: list[str] | None = None) -> int:
    """CLI do avaliador. `--check` valida o arquivo sem rede; sem argumentos = `--check`."""
    parser = argparse.ArgumentParser(prog="python -m tools.run_evals", description=__doc__)
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--check", action="store_true", help="valida os casos (sem rede)")
    grupo.add_argument(
        "--live", action="store_true", help="executa as APIs reais e grava evals/resultados/"
    )
    args = parser.parse_args(argv)

    if args.live:
        raise NotImplementedError("T17: --live será implementado na subtarefa 3")

    try:
        casos = load_casos(CASOS_PATH)
        verificar_cobertura(casos)
    except CasosError as exc:
        print(f"ERRO: {exc}")
        return 1
    print(f"OK: {len(casos)} casos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
