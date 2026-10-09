"""Testes unitários da normalização de `MetodoPagamento` (spec T10)."""

import pytest

from app.payment import MetodoPagamento, normalizar_metodo

M = MetodoPagamento


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("dinheiro", M.DINHEIRO),
        ("Dinheiro", M.DINHEIRO),
        ("espécie", M.DINHEIRO),
        ("cash", M.DINHEIRO),
        ("débito", M.DEBITO),
        ("cartao_de_debito", M.DEBITO),
        ("cartão de débito", M.DEBITO),
        ("cartao-de-debito", M.DEBITO),
        ("crédito", M.CREDITO_A_VISTA),
        ("cartão", M.CREDITO_A_VISTA),
        ("cartao de credito", M.CREDITO_A_VISTA),
        ("crédito à vista", M.CREDITO_A_VISTA),
        ("credito_a_vista", M.CREDITO_A_VISTA),
        ("parcelado", M.CREDITO_PARCELADO),
        ("crédito parcelado", M.CREDITO_PARCELADO),
        ("PIX", M.PIX),
        ("alipay", M.ALIPAY),
        ("Zhifubao", M.ALIPAY),
        ("WeChat", M.WECHAT_PAY),
        ("wechat pay", M.WECHAT_PAY),
        ("wechat_pay", M.WECHAT_PAY),
        ("weixin", M.WECHAT_PAY),
        ("boleto", M.OUTRO),
        ("", M.OUTRO),
        (None, M.OUTRO),
    ],
)
def test_normalizar_metodo(entrada, esperado):
    assert normalizar_metodo(entrada) is esperado
