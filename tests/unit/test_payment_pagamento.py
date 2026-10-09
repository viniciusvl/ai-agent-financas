"""Testes unitários dos validators e propriedades de `Pagamento` (spec T10)."""

from datetime import date, time
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain import Category, Currency
from app.payment import MAX_PARCELAS, MetodoPagamento, Pagamento

D = Decimal


def make(**overrides) -> Pagamento:
    """Pagamento válido; sobrescreva campos conforme o teste."""
    data = dict(
        metodo_pagamento="alipay",
        data=date(2026, 10, 8),
        valor_compra=D("35.50"),
        descricao="almoço",
        texto_original="almoço 35,5 no alipay",
    )
    data.update(overrides)
    return Pagamento(**data)


def test_normalizacoes_de_campos():
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


def test_moeda_e_categoria_none_viram_padrao():
    p = make(moeda=None, categoria=None)
    assert p.moeda is Currency.CNY
    assert p.categoria is Category.OUTROS


@pytest.mark.parametrize("valor", [0, -5, "abc", "", None])
def test_valor_compra_invalido(valor):
    with pytest.raises(ValidationError):
        make(valor_compra=valor)


@pytest.mark.parametrize("descricao", ["", "   ", None, 123, "x" * 201])
def test_descricao_invalida(descricao):
    with pytest.raises(ValidationError):
        make(descricao=descricao)


def test_quant_parcelas_none_vira_um():
    assert make(quant_parcelas=None).quant_parcelas == 1


def test_credito_a_vista_com_parcelas_vira_parcelado():
    p = make(metodo_pagamento="crédito", quant_parcelas=10, valor_compra="3000")
    assert p.metodo_pagamento is MetodoPagamento.CREDITO_PARCELADO
    assert p.quant_parcelas == 10
    assert p.valor_parcela == D("300.00")


def test_credito_a_vista_sem_parcelas_fica_uma():
    p = make(metodo_pagamento="credito_a_vista", quant_parcelas=1)
    assert p.metodo_pagamento is MetodoPagamento.CREDITO_A_VISTA
    assert p.quant_parcelas == 1


@pytest.mark.parametrize("n", [None, 0, 1, MAX_PARCELAS + 1, 30])
def test_credito_parcelado_com_quantidade_invalida(n):
    with pytest.raises(ValidationError):
        make(metodo_pagamento="credito_parcelado", quant_parcelas=n)


@pytest.mark.parametrize("metodo", ["debito", "dinheiro", "pix", "alipay", "wechat_pay", "outro"])
def test_outros_metodos_forcam_uma_parcela(metodo):
    p = make(metodo_pagamento=metodo, quant_parcelas=6)
    assert p.quant_parcelas == 1
    assert p.parcelas == [p.valor_compra]
    assert p.valor_parcela == p.valor_compra


def test_propriedades_de_parcelas():
    p = make(metodo_pagamento="credito_parcelado", quant_parcelas=3, valor_compra="100")
    assert p.parcelas == [D("33.34"), D("33.33"), D("33.33")]
    assert p.valor_primeira_parcela == D("33.34")
    assert p.valor_parcela == D("33.33")
    assert sum(p.parcelas) == D("100.00")


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
