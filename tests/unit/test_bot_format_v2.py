"""Testes unitários de formatação e do PendingStore genérico (T16, sessão 1)."""

from datetime import date, time
from decimal import Decimal

from app.bot import format_confirmacao, format_registrado
from app.messages import MSG_SAVED_HEADER
from app.payment import Pagamento
from app.pending_store import PendingExpense, PendingStore


def pagamento(**kw):
    data = dict(
        metodo_pagamento="pix",
        data=date(2026, 10, 9),
        hora=time(14, 7),
        valor_compra=Decimal("35"),
        moeda="BRL",
        categoria="alimentação",
        descricao="almoço",
    )
    data.update(kw)
    return Pagamento(**data)


def test_confirmacao_simples_sem_parcelas():
    text = format_confirmacao(pagamento())
    assert text == (
        "📝 <b>Confirme o pagamento:</b>\n"
        "• Valor: R$ 35,00\n"
        "• Pagamento: Pix\n"
        "• Categoria: alimentação\n"
        "• Descrição: almoço\n"
        "• Data: 09/10/2026 14:07"
    )


def test_confirmacao_parcelas_iguais():
    text = format_confirmacao(
        pagamento(
            metodo_pagamento="credito_parcelado",
            quant_parcelas=10,
            valor_compra="3000",
            moeda="BRL",
        )
    )
    assert "• Pagamento: crédito parcelado em 10x de R$ 300,00" in text


def test_confirmacao_parcelas_desiguais_sem_hora():
    text = format_confirmacao(
        pagamento(
            metodo_pagamento="credito_parcelado",
            quant_parcelas=3,
            valor_compra="100",
            moeda="BRL",
            hora=None,
        )
    )
    assert "• Pagamento: crédito parcelado em 3x (1ª de R$ 33,34 + 2x de R$ 33,33)" in text
    assert text.endswith("• Data: 09/10/2026")


def test_confirmacao_escapa_descricao():
    text = format_confirmacao(pagamento(descricao="<b>tênis</b> & meia"))
    assert "• Descrição: &lt;b&gt;tênis&lt;/b&gt; &amp; meia" in text


def test_registrado_troca_cabecalho():
    p = pagamento()
    linhas = format_confirmacao(p).split("\n")
    assert format_registrado(p) == "\n".join([MSG_SAVED_HEADER, *linhas[1:]])


def test_pending_store_generico_roundtrip(tmp_path):
    store = PendingStore(str(tmp_path / "bot.db"), model=Pagamento)
    store.init()
    p = pagamento(metodo_pagamento="credito_parcelado", quant_parcelas=4, valor_compra="35")
    pending_id = store.save(1, 2, p)
    item = store.get(pending_id)
    assert isinstance(item, PendingExpense)
    assert item.expense == p
    assert item.expense.valor_parcela == Decimal("8.75")


def test_pending_store_modelo_padrao_é_expense():
    assert PendingStore.__init__.__defaults__[-1].__name__ == "Expense"
