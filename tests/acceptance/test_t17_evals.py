import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.domain import Currency
from app.payment import MetodoPagamento, Pagamento
from app.payment_extractor import ResultadoExtracao
from app.router import Intencao, Rota
from tools.run_evals import (
    CAMPOS_AVALIADOS,
    CASOS_PATH,
    Caso,
    CasosError,
    avaliar,
    load_casos,
    main,
    render_relatorio,
    verificar_cobertura,
)

pytestmark = pytest.mark.task("T17")

ROOT = Path(__file__).resolve().parents[2]
RECEBIDO = datetime(2026, 10, 9, 2, 0, tzinfo=ZoneInfo("UTC"))


# --- casos do repositório -----------------------------------------------------------------------


def test_repo_cases_load_and_cover():
    casos = load_casos(CASOS_PATH)
    verificar_cobertura(casos)
    assert len(casos) >= 60
    assert len({c.id for c in casos}) == len(casos)
    rotas = Counter(c.rota for c in casos)
    assert rotas["escrita"] >= 30 and rotas["leitura"] >= 15 and rotas["outro"] >= 10
    metodos = Counter(c.esperado.get("metodo_pagamento") for c in casos if c.rota == "escrita")
    for metodo in MetodoPagamento:
        assert metodos[metodo.value] >= 2, metodo
    moedas = Counter(c.esperado.get("moeda") for c in casos if c.esperado.get("moeda"))
    for moeda in Currency:
        assert moedas[moeda.value] >= 3, moeda
    assert moedas.most_common(1)[0][1] >= 10
    parcelas = [
        c.esperado["quant_parcelas"]
        for c in casos
        if c.esperado.get("metodo_pagamento") == "credito_parcelado"
        and "quant_parcelas" in c.esperado
    ]
    assert len(parcelas) >= 6 and len(set(parcelas)) >= 4
    assert all("valor_compra" in c.esperado for c in casos if c.rota == "escrita")


def test_check_cli():
    result = subprocess.run(
        [sys.executable, "-m", "tools.run_evals", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().startswith("OK:")


# --- validação ----------------------------------------------------------------------------------


def write(tmp_path, body):
    path = tmp_path / "casos.yaml"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        (
            'casos:\n  - {id: x1, texto: "a", rota: escrita, esperado: {valor_compra: 1}}\n'
            '  - {id: x1, texto: "b", rota: outro}\n',
            "x1",
        ),
        ('casos:\n  - {id: x2, texto: "", rota: outro}\n', "x2"),
        ('casos:\n  - {id: x3, texto: "a", rota: comprar}\n', "x3"),
        ('casos:\n  - {id: x4, texto: "a", rota: escrita, esperado: {cor: azul}}\n', "x4"),
        ('casos:\n  - {id: x5, texto: "a", rota: leitura, esperado: {moeda: BRL}}\n', "x5"),
    ],
)
def test_load_casos_validation(tmp_path, body, fragment):
    with pytest.raises(CasosError, match=fragment):
        load_casos(write(tmp_path, body))


def test_coverage_failure_is_reported():
    casos = [Caso(id="a", texto="oi", rota="outro")]
    with pytest.raises(CasosError):
        verificar_cobertura(casos)


def test_main_check_returns_1_on_invalid(tmp_path, monkeypatch, capsys):
    import tools.run_evals as module

    monkeypatch.setattr(module, "CASOS_PATH", write(tmp_path, "casos: []\n"))
    assert main(["--check"]) == 1


# --- avaliação ----------------------------------------------------------------------------------


class FakeRouter:
    def __init__(self, respostas):
        self.respostas = respostas

    async def route(self, texto):
        resposta = self.respostas[texto]
        if isinstance(resposta, Exception):
            raise resposta
        return Rota(Intencao(resposta), 0.9, origem="jev")


class FakeExtractor:
    def __init__(self, respostas):
        self.respostas = respostas

    async def extract(self, texto, recebido_em):
        return self.respostas[texto]


def pag(**kw):
    data = dict(data=date(2026, 10, 9), descricao="x", valor_compra=Decimal("80"), moeda="BRL")
    data.update(kw)
    return Pagamento(**data)


async def test_avaliar_metrics():
    casos = [
        Caso("c1", "taxi 80", "escrita", {"valor_compra": 80, "moeda": "BRL"}),
        Caso(
            "c2",
            "celular 10x",
            "escrita",
            {"valor_compra": 3000, "metodo_pagamento": "credito_parcelado", "quant_parcelas": 10},
        ),
        Caso("c3", "quanto gastei", "leitura"),
        Caso("c4", "oi", "outro"),
        Caso("c5", "pão 5", "escrita", {"valor_compra": 5}),
    ]
    router = FakeRouter(
        {
            "taxi 80": "escrita",
            "celular 10x": "escrita",
            "quanto gastei": "escrita",  # erro de rota
            "oi": RuntimeError("down"),  # exceção = erro
            "pão 5": "escrita",
        }
    )
    extractor = FakeExtractor(
        {
            "taxi 80": ResultadoExtracao(pagamento=pag()),
            "celular 10x": ResultadoExtracao(
                pagamento=pag(
                    valor_compra=Decimal("3000"),
                    metodo_pagamento="credito_parcelado",
                    quant_parcelas=12,  # erro de campo
                )
            ),
            "pão 5": ResultadoExtracao(erro="não entendi"),  # sem pagamento
        }
    )
    rel = await avaliar(casos, router, extractor, RECEBIDO)
    assert rel.total == 5
    assert rel.acuracia_rota == pytest.approx(3 / 5)
    # campos: c1 2/2, c2 2/3, c5 0/1 → 4/6
    assert rel.acuracia_campos == pytest.approx(4 / 6)
    assert rel.acertos_por_campo["valor_compra"] == pytest.approx(2 / 3)
    assert rel.acertos_por_campo["quant_parcelas"] == 0.0
    assert rel.latencia_media_ms >= 0
    ids = " ".join(rel.falhas)
    assert "c3" in ids and "c4" in ids and "c2" in ids and "c5" in ids and "c1" not in ids


def test_render_relatorio():
    from tools.run_evals import Relatorio

    rel = Relatorio(
        total=10,
        acuracia_rota=0.95,
        acuracia_campos=0.875,
        acertos_por_campo={c: 1.0 for c in CAMPOS_AVALIADOS},
        latencia_media_ms=812.4,
        falhas=["e007: rota leitura ≠ escrita"],
    )
    md = render_relatorio(rel, datetime(2026, 10, 9, 14, 30))
    assert md.startswith("# Evals — 2026-10-09 14:30")
    assert "95.0%" in md and "87.5%" in md
    assert "e007: rota leitura ≠ escrita" in md
