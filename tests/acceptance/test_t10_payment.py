import random
from datetime import date, time
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain import Category, Currency
from app.payment import MAX_PARCELAS, MetodoPagamento, Pagamento, calcular_parcelas

pytestmark = pytest.mark.task("T10")

D = Decimal


def make(**overrides):
    data = dict(
        metodo_pagamento="pix",
        data=date(2026, 10, 8),
        valor_compra=D("35.50"),
        descricao="almoço",
        texto_original="almoço 35,5 no pix",
    )
    data.update(overrides)
    return Pagamento(**data)


# --- calcular_parcelas -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "n", "esperado"),
    [
        ("100.00", 3, ["33.34", "33.33", "33.33"]),
        ("10.00", 4, ["2.50", "2.50", "2.50", "2.50"]),
        ("0.05", 2, ["0.03", "0.02"]),
        ("99.99", 1, ["99.99"]),
        ("1000.00", 7, ["142.90"] + ["142.85"] * 6),
    ],
)
def test_calcular_parcelas_exemplos(valor, n, esperado):
    assert calcular_parcelas(D(valor), n) == [D(x) for x in esperado]


def test_calcular_parcelas_propriedades():
    rng = random.Random(20261008)
    for _ in range(1000):
        valor = D(rng.randint(1, 10_000_000)) / 100
        n = rng.randint(1, MAX_PARCELAS)
        parcelas = calcular_parcelas(valor, n)
        assert len(parcelas) == n
        assert sum(parcelas) == valor
        assert all(p.as_tuple().exponent == -2 for p in parcelas)
        assert max(parcelas) - min(parcelas) <= D("0.01") * n
        assert parcelas[1:] == [parcelas[-1]] * (n - 1)
        assert parcelas[0] >= parcelas[-1]


@pytest.mark.parametrize("n", [0, -1, MAX_PARCELAS + 1])
def test_calcular_parcelas_quantidade_invalida(n):
    with pytest.raises(ValueError):
        calcular_parcelas(D("100"), n)


# --- MetodoPagamento ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Dinheiro", MetodoPagamento.DINHEIRO),
        ("espécie", MetodoPagamento.DINHEIRO),
        ("cash", MetodoPagamento.DINHEIRO),
        ("Débito", MetodoPagamento.DEBITO),
        ("cartão de débito", MetodoPagamento.DEBITO),
        ("crédito", MetodoPagamento.CREDITO_A_VISTA),
        ("cartao", MetodoPagamento.CREDITO_A_VISTA),
        ("credito_a_vista", MetodoPagamento.CREDITO_A_VISTA),
        ("crédito à vista", MetodoPagamento.CREDITO_A_VISTA),
        ("parcelado", MetodoPagamento.CREDITO_PARCELADO),
        ("PIX", MetodoPagamento.PIX),
        ("cheque", MetodoPagamento.OUTRO),
        (None, MetodoPagamento.OUTRO),
    ],
)
def test_metodo_normalizado(entrada, esperado):
    kwargs = {"metodo_pagamento": entrada}
    if esperado is MetodoPagamento.CREDITO_PARCELADO:
        kwargs["quant_parcelas"] = 3
    assert make(**kwargs).metodo_pagamento is esperado


# --- Pagamento ---------------------------------------------------------------------------------


def test_campos_basicos_e_normalizacoes():
    p = make(
        valor_compra="1.234,56",
        moeda="reais",
        categoria="ALIMENTACAO",
        descricao="  jantar  ",
        hora=time(20, 15),
    )
    assert p.valor_compra == D("1234.56")
    assert p.moeda is Currency.BRL
    assert p.categoria is Category.ALIMENTACAO
    assert p.descricao == "jantar"
    assert p.hora == time(20, 15)
    assert p.quant_parcelas == 1
    assert make(moeda=None, categoria=None).categoria is Category.OUTROS


@pytest.mark.parametrize("valor", [0, -5, "abc", ""])
def test_valor_invalido(valor):
    with pytest.raises(ValidationError):
        make(valor_compra=valor)


@pytest.mark.parametrize("descricao", ["", "   ", None, 123, "x" * 201])
def test_descricao_invalida(descricao):
    with pytest.raises(ValidationError):
        make(descricao=descricao)


def test_parcelado_calcula_valores():
    p = make(metodo_pagamento="credito_parcelado", quant_parcelas=3, valor_compra="100")
    assert p.parcelas == [D("33.34"), D("33.33"), D("33.33")]
    assert p.valor_parcela == D("33.33")
    assert p.valor_primeira_parcela == D("33.34")


def test_credito_a_vista_com_parcelas_vira_parcelado():
    p = make(metodo_pagamento="crédito", quant_parcelas=10, valor_compra="3000")
    assert p.metodo_pagamento is MetodoPagamento.CREDITO_PARCELADO
    assert p.valor_parcela == D("300.00")


@pytest.mark.parametrize("n", [None, 0, 1, 25, 30])
def test_parcelado_com_quantidade_invalida(n):
    with pytest.raises(ValidationError):
        make(metodo_pagamento="credito_parcelado", quant_parcelas=n)


@pytest.mark.parametrize("metodo", ["debito", "dinheiro", "pix", "outro"])
def test_outros_metodos_forcam_uma_parcela(metodo):
    p = make(metodo_pagamento=metodo, quant_parcelas=6)
    assert p.quant_parcelas == 1
    assert p.parcelas == [p.valor_compra]
    assert p.valor_parcela == p.valor_compra


def test_valor_parcela_externo_e_ignorado():
    p = make(
        metodo_pagamento="credito_parcelado",
        quant_parcelas=4,
        valor_compra="100",
        valor_parcela="999",
    )
    assert p.valor_parcela == D("25.00")
    assert "valor_parcela" not in p.model_dump()


def test_roundtrip_json():
    p = make(metodo_pagamento="credito_parcelado", quant_parcelas=2, hora=time(9, 30))
    assert Pagamento.model_validate_json(p.model_dump_json()) == p
