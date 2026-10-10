import inspect
import re
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.task("T18")

ROOT = Path(__file__).resolve().parents[2]
PROIBIDOS = re.compile(
    r"china|chin[eê]s|xangai|shanghai|kuai|yuan|rmb|\bcny\b|¥|alipay|wechat|weixin|zhifubao|viagem",
    re.IGNORECASE,
)


def _arquivos_versionados() -> list[Path]:
    saida = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout
    ignorados = {Path(__file__).resolve(), (ROOT / "specs/tasks/T18-generalizacao.md").resolve()}
    arquivos = []
    for linha in saida.splitlines():
        if linha.startswith(".agent/"):
            continue
        caminho = (ROOT / linha).resolve()
        if caminho in ignorados or not caminho.is_file():
            continue
        arquivos.append(caminho)
    return arquivos


def test_nenhuma_mencao_a_viagem_ou_china():
    ocorrencias = []
    for caminho in _arquivos_versionados():
        try:
            texto = caminho.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for numero, linha in enumerate(texto.splitlines(), start=1):
            if PROIBIDOS.search(linha):
                ocorrencias.append(f"{caminho.relative_to(ROOT)}:{numero}: {linha.strip()[:80]}")
    assert not ocorrencias, "menções encontradas:\n" + "\n".join(ocorrencias[:40])


# --- moedas -------------------------------------------------------------------------------------


def test_moedas():
    from app.domain import Currency, Expense

    assert {c.value for c in Currency} == {"BRL", "USD", "EUR"}

    def moeda(valor):
        return Expense(amount=10, description="x", spent_at="2026-10-09", currency=valor).currency

    assert moeda(None) is Currency.BRL
    for alias in ("eur", "€", "Euro", "euros"):
        assert moeda(alias) is Currency.EUR
    assert moeda("R$") is Currency.BRL
    assert moeda("US$") is Currency.USD
    for invalida in ("cny", "yuan", "XYZ"):
        with pytest.raises(ValidationError):
            moeda(invalida)
    assert Expense(amount=10, description="x", spent_at="2026-10-09").currency is Currency.BRL


def test_payment_method_v1():
    from app.domain import Expense, PaymentMethod

    assert {m.value for m in PaymentMethod} == {"dinheiro", "cartão", "pix", "outro"}

    def metodo(valor):
        return Expense(
            amount=10, description="x", spent_at="2026-10-09", payment_method=valor
        ).payment_method

    assert metodo("PIX") is PaymentMethod.PIX
    assert metodo("alipay") is PaymentMethod.OUTRO


# --- pagamento v2 ------------------------------------------------------------------------------


def test_metodos_v2_e_aliases():
    from app.payment import MetodoPagamento, Pagamento

    assert {m.value for m in MetodoPagamento} == {
        "dinheiro",
        "debito",
        "credito_a_vista",
        "credito_parcelado",
        "pix",
        "boleto",
        "transferencia",
        "outro",
    }

    def metodo(valor):
        return Pagamento(
            data="2026-10-09", valor_compra=10, descricao="x", metodo_pagamento=valor
        ).metodo_pagamento

    for alias in ("boleto", "Boleto bancário"):
        assert metodo(alias) is MetodoPagamento.BOLETO
    for alias in ("transferência", "transferencia bancaria", "TED", "doc"):
        assert metodo(alias) is MetodoPagamento.TRANSFERENCIA
    for antigo in ("alipay", "wechat", "wechat_pay", "weixin", "zhifubao"):
        assert metodo(antigo) is MetodoPagamento.OUTRO


def test_pagamento_moeda_padrao_brl():
    from app.domain import Currency
    from app.payment import Pagamento

    p = Pagamento(data="2026-10-09", valor_compra=10, descricao="x", moeda=None)
    assert p.moeda is Currency.BRL
    assert Pagamento(data="2026-10-09", valor_compra=10, descricao="x").moeda is Currency.BRL


def test_labels_do_bot():
    from app.bot import METODO_LABEL
    from app.payment import MetodoPagamento

    assert set(METODO_LABEL) == set(MetodoPagamento)
    assert METODO_LABEL[MetodoPagamento.BOLETO] == "boleto"
    assert METODO_LABEL[MetodoPagamento.TRANSFERENCIA] == "transferência"


# --- padrões -----------------------------------------------------------------------------------


def _padrao(cls, nome):
    return inspect.signature(cls).parameters[nome].default


def test_padroes_de_fuso_e_moeda():
    from app.bot import BotService
    from app.config import Settings
    from app.extractor import ExpenseExtractor
    from app.payment_extractor import PaymentExtractor
    from app.read_agent import ReadAgent

    assert _padrao(PaymentExtractor, "timezone") == "America/Sao_Paulo"
    assert _padrao(PaymentExtractor, "default_currency") == "BRL"
    assert _padrao(ExpenseExtractor, "default_currency") == "BRL"
    assert _padrao(ReadAgent, "timezone") == "America/Sao_Paulo"
    assert _padrao(BotService, "timezone") == "America/Sao_Paulo"
    settings = Settings(_env_file=None)
    assert settings.timezone == "America/Sao_Paulo"
    assert settings.default_currency == "BRL"


def test_queries_euro_e_registro_brl():
    from datetime import date

    from app.queries import Registro, format_valor

    assert format_valor("EUR", Decimal("1234.56")) == "€ 1.234,56"
    assert format_valor("BRL", Decimal("10")) == "R$ 10,00"
    assert Registro(data=date(2026, 10, 9), valor_compra=Decimal("1")).moeda == "BRL"


# --- nome do projeto e deploy ------------------------------------------------------------------


def test_titulo_do_app():
    from app.config import Settings
    from app.main import create_app

    class Fake:
        async def handle_update(self, update):
            pass

    app = create_app(Settings(_env_file=None, telegram_webhook_secret="s"), service=Fake())
    assert app.title == "ai-agent-financas"


def test_arquivos_do_nginx_renomeados():
    nginx = ROOT / "deploy" / "nginx"
    assert (nginx / "ai-agent-financas.conf").is_file()
    assert (nginx / "ai-agent-financas.http-only.conf").is_file()
    assert sorted(p.name for p in nginx.glob("*.conf")) == [
        "ai-agent-financas.conf",
        "ai-agent-financas.http-only.conf",
    ]
    assert "ai-agent-financas.conf" in (ROOT / "docs" / "deploy.md").read_text(encoding="utf-8")
