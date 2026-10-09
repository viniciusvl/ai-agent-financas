"""Testes unitários de `load_casos` do avaliador (spec T17)."""

from pathlib import Path

import pytest

from tools.run_evals import CASOS_PATH, Caso, CasosError, load_casos


def _escrever(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "casos.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_carrega_repo_tem_ao_menos_30_casos():
    casos = load_casos(CASOS_PATH)
    assert len(casos) >= 30
    assert all(isinstance(c, Caso) for c in casos)


def test_campos_opcionais_tem_default():
    caso = Caso(id="a", texto="oi", rota="outro")
    assert caso.esperado == {}


def test_esperado_vazio_em_leitura_e_aceito(tmp_path):
    casos = load_casos(_escrever(tmp_path, "casos:\n  - {id: l1, texto: 'total', rota: leitura}\n"))
    assert casos == [Caso(id="l1", texto="total", rota="leitura")]


@pytest.mark.parametrize(
    "body",
    [
        "casos: []\n",  # lista vazia é formato válido (a cobertura é outro passo)
        "outra: []\n",  # falta a chave 'casos'
        "casos: nope\n",  # 'casos' não é lista
    ],
)
def test_formato_de_topo(tmp_path, body):
    if body == "casos: []\n":
        assert load_casos(_escrever(tmp_path, body)) == []
    else:
        with pytest.raises(CasosError):
            load_casos(_escrever(tmp_path, body))


def test_arquivo_ausente_gera_casos_error(tmp_path):
    with pytest.raises(CasosError):
        load_casos(tmp_path / "nao_existe.yaml")


def test_esperado_nao_mapeamento_gera_erro(tmp_path):
    body = "casos:\n  - {id: e1, texto: 'x', rota: escrita, esperado: [1, 2]}\n"
    with pytest.raises(CasosError, match="e1"):
        load_casos(_escrever(tmp_path, body))
