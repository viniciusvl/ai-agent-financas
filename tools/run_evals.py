"""Avaliação (evals) do roteador e do extrator de pagamentos.

Uso:
    python -m tools.run_evals --check   # valida evals/casos.yaml (formato + cobertura), sem rede
    python -m tools.run_evals --live    # chama as APIs reais e grava evals/resultados/AAAA-MM-DD.md

Spec: specs/tasks/T17-evals.md
"""

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from app.config import get_settings
from app.payment_extractor import PaymentExtractor
from app.router import DeepSeekIntentFallback, IntentRouter
from app.sheet_schema import SheetSchema

CASOS_PATH = Path(__file__).resolve().parents[1] / "evals" / "casos.yaml"
RESULTADOS_DIR = CASOS_PATH.parent / "resultados"
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


def _campo_confere(obtido: Any, esperado: Any) -> bool:
    """Compara um campo extraído com o valor esperado do caso (spec T17).

    `valor_compra` é `Decimal` (compara via `Decimal(str(esperado))`); campos de enum
    (`moeda`, `metodo_pagamento`, `categoria`) comparam pelo `.value`.
    """
    if isinstance(obtido, Decimal):
        try:
            return obtido == Decimal(str(esperado))
        except (InvalidOperation, ValueError):
            return False
    if isinstance(obtido, Enum):
        return str(obtido.value) == str(esperado)
    return obtido == esperado


def _motivo_rota(obtido: Any, esperado: str, erro: Exception | None) -> str:
    """Descrição curta da falha de roteamento de um caso."""
    if erro is not None:
        return f"rota {esperado} ≠ erro ({type(erro).__name__})"
    return f"rota {esperado} ≠ {obtido}"


async def avaliar(
    casos: list[Caso], router: Any, extractor: Any, recebido_em: datetime
) -> Relatorio:
    """Avalia roteador e extrator sobre os casos; exceções viram erro do caso.

    Para cada caso de rota escrita, extrai o pagamento e confere apenas os campos
    presentes em `esperado`. A latência medida é a de `route` (+ `extract`) por caso.
    """
    total = len(casos)
    acertos_rota = 0
    campos_total = 0
    campos_acertos = 0
    acertos_campo: Counter[str] = Counter()
    total_campo: Counter[str] = Counter()
    falhas: list[str] = []
    latencias_ms: list[float] = []

    for caso in casos:
        inicio = perf_counter()
        erro_rota: Exception | None = None
        rota_obtida: Any = None
        try:
            rota = await router.route(caso.texto)
            rota_obtida = rota.intencao.value
        except Exception as exc:  # noqa: BLE001 - qualquer exceção é erro do caso
            erro_rota = exc

        resultado = None
        if caso.rota == "escrita":
            try:
                resultado = await extractor.extract(caso.texto, recebido_em)
            except Exception:  # noqa: BLE001 - falha de extração = todos os campos errados
                resultado = None

        latencias_ms.append((perf_counter() - inicio) * 1000)

        if erro_rota is None and rota_obtida == caso.rota:
            acertos_rota += 1
        else:
            falhas.append(f"{caso.id}: {_motivo_rota(rota_obtida, caso.rota, erro_rota)}")

        if not caso.esperado:
            continue

        pagamento = resultado.pagamento if resultado is not None else None
        campos_errados: list[str] = []
        for campo, valor_esperado in caso.esperado.items():
            total_campo[campo] += 1
            campos_total += 1
            if pagamento is not None and _campo_confere(getattr(pagamento, campo), valor_esperado):
                campos_acertos += 1
                acertos_campo[campo] += 1
            else:
                campos_errados.append(campo)
        if campos_errados:
            falhas.append(f"{caso.id}: campos incorretos: {', '.join(campos_errados)}")

    acertos_por_campo = {
        campo: acertos_campo[campo] / avaliados for campo, avaliados in total_campo.items()
    }
    return Relatorio(
        total=total,
        acuracia_rota=acertos_rota / total if total else 0.0,
        acuracia_campos=campos_acertos / campos_total if campos_total else 0.0,
        acertos_por_campo=acertos_por_campo,
        latencia_media_ms=sum(latencias_ms) / len(latencias_ms) if latencias_ms else 0.0,
        falhas=falhas,
    )


def render_relatorio(rel: Relatorio, quando: datetime) -> str:
    """Renderiza o relatório de avaliação em Markdown (spec T17)."""
    linhas = [
        f"# Evals — {quando:%Y-%m-%d %H:%M}",
        "",
        f"- Casos avaliados: {rel.total}",
        f"- Acurácia de rota: {rel.acuracia_rota:.1%} (limiar {LIMIAR_ROTA:.0%})",
        f"- Acurácia de campos: {rel.acuracia_campos:.1%} (limiar {LIMIAR_CAMPOS:.0%})",
        f"- Latência média: {rel.latencia_media_ms:.1f} ms",
        "",
        "## Acertos por campo",
        "",
    ]
    for campo, acerto in rel.acertos_por_campo.items():
        linhas.append(f"- {campo}: {acerto:.1%}")

    linhas += ["", "## Falhas", ""]
    if rel.falhas:
        linhas.extend(f"- {falha}" for falha in rel.falhas)
    else:
        linhas.append("- (nenhuma)")

    return "\n".join(linhas) + "\n"


async def _rodar_live(
    casos: list[Caso], router: IntentRouter, extractor: PaymentExtractor, recebido_em: datetime
) -> Relatorio:
    """Executa `avaliar` com as APIs reais e fecha o client HTTP do roteador ao final."""
    try:
        return await avaliar(casos, router, extractor, recebido_em)
    finally:
        await router.aclose()


def _executar_live() -> int:
    """Roda a avaliação ao vivo, grava `evals/resultados/<AAAA-MM-DD>.md` e aplica os limiares."""
    settings = get_settings()
    casos = load_casos(CASOS_PATH)
    verificar_cobertura(casos)

    schema = SheetSchema.load(settings.sheet_schema_path)
    fallback = DeepSeekIntentFallback(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
    )
    router = IntentRouter(
        api_key=settings.typesafe_api_key,
        model=settings.jev_model,
        base_url=settings.jev_base_url,
        threshold=settings.router_confidence_threshold,
        fallback=fallback,
    )
    extractor = PaymentExtractor(
        api_key=settings.deepseek_api_key,
        schema=schema,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        default_currency=settings.default_currency,
        timezone=settings.timezone,
    )

    recebido_em = datetime.now(ZoneInfo(settings.timezone))
    rel = asyncio.run(_rodar_live(casos, router, extractor, recebido_em))

    destino = RESULTADOS_DIR / f"{recebido_em:%Y-%m-%d}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(render_relatorio(rel, recebido_em), encoding="utf-8")
    print(f"Relatório gravado em {destino}")

    aprovado = rel.acuracia_rota >= LIMIAR_ROTA and rel.acuracia_campos >= LIMIAR_CAMPOS
    return 0 if aprovado else 1


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
        try:
            return _executar_live()
        except CasosError as exc:
            print(f"ERRO: {exc}")
            return 1

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
