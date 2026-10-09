"""Testes unitários de `calcular_parcelas` (spec T10)."""

from decimal import Decimal

import pytest

from app.payment import MAX_PARCELAS, calcular_parcelas

D = Decimal


@pytest.mark.parametrize(
    ("valor", "n", "esperado"),
    [
        ("100.00", 3, ["33.34", "33.33", "33.33"]),
        ("0.05", 2, ["0.03", "0.02"]),
        ("7.77", 7, ["1.11"] * 7),
    ],
)
def test_exemplos(valor, n, esperado):
    assert calcular_parcelas(D(valor), n) == [D(x) for x in esperado]


def test_soma_exata_e_duas_casas():
    parcelas = calcular_parcelas(D("1000.00"), 7)
    assert sum(parcelas) == D("1000.00")
    assert all(p.as_tuple().exponent == -2 for p in parcelas)


@pytest.mark.parametrize("n", [0, -1, MAX_PARCELAS + 1])
def test_quantidade_fora_do_intervalo(n):
    with pytest.raises(ValueError):
        calcular_parcelas(D("100"), n)


@pytest.mark.parametrize("n", ["3", None, 2.0, True])
def test_quantidade_de_tipo_invalido(n):
    with pytest.raises(ValueError):
        calcular_parcelas(D("100"), n)


@pytest.mark.parametrize("valor", [D("0"), D("-1"), 0])
def test_valor_nao_positivo(valor):
    with pytest.raises(ValueError):
        calcular_parcelas(valor, 2)
