"""Testes unitários de `verificar_cobertura` do avaliador (spec T17)."""

import pytest

from tools.run_evals import (
    CASOS_PATH,
    METODOS_PAGAMENTO,
    MIN_PARCELAS_DISTINTAS,
    Caso,
    CasosError,
    load_casos,
    main,
    verificar_cobertura,
)


def _escrita(cid: str, **esperado) -> Caso:
    return Caso(id=cid, texto=f"gasto {cid}", rota="escrita", esperado=dict(esperado))


def _casos_com_cobertura() -> list[Caso]:
    """Conjunto mínimo que cumpre exatamente a cobertura exigida."""
    casos: list[Caso] = []
    # 30 escrita: 8 métodos × 2 + crédito parcelado extra (2 já cobertos no par).
    # A moeda mais frequente (BRL) precisa aparecer >= 10 vezes.
    metodos = list(METODOS_PAGAMENTO)
    for i in range(30):
        metodo = metodos[i % len(metodos)]
        casos.append(
            _escrita(f"e{i:03d}", valor_compra=10 + i, moeda="BRL", metodo_pagamento=metodo),
        )
    # crédito parcelado com parcelas distintas (>= 6 casos, >= 4 valores).
    for i, parcela in enumerate((2, 3, 4, 5, 6, 7)):
        casos.append(
            _escrita(
                f"p{i:03d}",
                valor_compra=100 + i,
                moeda="BRL",
                metodo_pagamento="credito_parcelado",
                quant_parcelas=parcela,
            )
        )
    # moedas que ainda faltam (cada Currency >= 3).
    casos += [
        _escrita("u1", valor_compra=6, moeda="USD"),
        _escrita("u2", valor_compra=7, moeda="USD"),
        _escrita("u3", valor_compra=8, moeda="USD"),
        _escrita("x1", valor_compra=9, moeda="EUR"),
        _escrita("x2", valor_compra=10, moeda="EUR"),
        _escrita("x3", valor_compra=11, moeda="EUR"),
    ]
    casos += [Caso(id=f"l{i}", texto="quanto gastei", rota="leitura") for i in range(15)]
    casos += [Caso(id=f"o{i}", texto="oi", rota="outro") for i in range(10)]
    return casos


def test_repo_passa_na_cobertura():
    verificar_cobertura(load_casos(CASOS_PATH))


def test_conjunto_minimo_passa():
    verificar_cobertura(_casos_com_cobertura())


def test_falta_de_rota_escrita_e_reportada():
    casos = [Caso(id="o1", texto="oi", rota="outro")]
    with pytest.raises(CasosError, match="escrita"):
        verificar_cobertura(casos)


def test_escrita_sem_valor_compra_e_reportada():
    casos = _casos_com_cobertura()
    casos[0].esperado.pop("valor_compra")
    with pytest.raises(CasosError, match="valor_compra"):
        verificar_cobertura(casos)


def test_metodo_de_pagamento_insuficiente_e_reportado():
    casos = _casos_com_cobertura()
    # Remove todas as ocorrências de 'pix' preservando a contagem mínima de escrita.
    alvo = [c for c in casos if c.esperado.get("metodo_pagamento") == "pix"]
    for caso in alvo:
        caso.esperado.pop("metodo_pagamento")
    with pytest.raises(CasosError, match="pix"):
        verificar_cobertura(casos)


def test_moeda_insuficiente_e_reportada():
    casos = _casos_com_cobertura()
    for caso in casos:
        if caso.esperado.get("moeda") == "BRL":
            caso.esperado.pop("moeda")
    with pytest.raises(CasosError, match="BRL"):
        verificar_cobertura(casos)


def test_parcelas_distintas_insuficientes_e_reportadas():
    casos = _casos_com_cobertura()
    parcelados = [c for c in casos if "quant_parcelas" in c.esperado]
    # Mantém 6 casos parcelados, mas todos com o mesmo valor de parcela.
    for caso in parcelados:
        caso.esperado["quant_parcelas"] = 2
    with pytest.raises(CasosError, match="distintos"):
        verificar_cobertura(casos)
    assert MIN_PARCELAS_DISTINTAS >= 4


def test_main_check_usa_casos_path_do_modulo(tmp_path, monkeypatch):
    import tools.run_evals as module

    path = tmp_path / "casos.yaml"
    path.write_text("casos: []\n", encoding="utf-8")
    monkeypatch.setattr(module, "CASOS_PATH", path)
    assert main(["--check"]) == 1
    assert main([]) == 1
