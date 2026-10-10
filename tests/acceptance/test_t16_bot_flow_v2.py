from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app import messages as M
from app.bot import BotService, format_confirmacao, format_registrado
from app.extractor import ExtractionError
from app.payment import Pagamento
from app.payment_extractor import ResultadoExtracao
from app.pending_store import PendingExpense, PendingStore
from app.queries import ReadError
from app.router import Intencao, Rota, RouterError
from app.sheets import SheetsError
from app.stt import TranscriptionError
from app.telegram_api import confirmation_keyboard

pytestmark = pytest.mark.task("T16")

NOW = datetime(2026, 10, 9, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
MSG_TS = 1791504000  # 2026-10-09 00:00:00 UTC
OWNER = 111


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


# --- formatação ---------------------------------------------------------------------------------


def test_format_confirmacao_parcelado():
    p = pagamento(
        metodo_pagamento="credito_parcelado",
        quant_parcelas=10,
        valor_compra="3000",
        moeda="BRL",
        categoria="compras",
        descricao="celular",
        data=date(2026, 10, 8),
    )
    assert format_confirmacao(p) == (
        "📝 <b>Confirme o pagamento:</b>\n"
        "• Valor: R$ 3.000,00\n"
        "• Pagamento: crédito parcelado em 10x de R$ 300,00\n"
        "• Categoria: compras\n"
        "• Descrição: celular\n"
        "• Data: 08/10/2026 14:07"
    )


def test_format_confirmacao_parcelas_desiguais_e_sem_hora():
    p = pagamento(
        metodo_pagamento="credito_parcelado",
        quant_parcelas=3,
        valor_compra="100",
        moeda="BRL",
        hora=None,
        descricao="<b>tênis</b> & meia",
    )
    text = format_confirmacao(p)
    assert "• Pagamento: crédito parcelado em 3x (1ª de R$ 33,34 + 2x de R$ 33,33)" in text
    assert "• Descrição: &lt;b&gt;tênis&lt;/b&gt; &amp; meia" in text
    assert text.endswith("• Data: 09/10/2026")


def test_format_confirmacao_simples():
    text = format_confirmacao(pagamento(metodo_pagamento="debito"))
    assert "• Valor: R$ 35,00" in text
    assert "• Pagamento: débito\n" in text


def test_format_registrado():
    p = pagamento()
    linhas = format_confirmacao(p).split("\n")
    assert format_registrado(p) == "\n".join([M.MSG_SAVED_HEADER, *linhas[1:]])


# --- PendingStore genérico ----------------------------------------------------------------------


def test_pending_store_with_pagamento_model(tmp_path):
    store = PendingStore(str(tmp_path / "bot.db"), model=Pagamento)
    store.init()
    p = pagamento(metodo_pagamento="credito_parcelado", quant_parcelas=4)
    pending_id = store.save(1, 2, p)
    item = store.get(pending_id)
    assert isinstance(item, PendingExpense)
    assert item.expense == p
    assert item.expense.valor_parcela == Decimal("8.75")


# --- fakes --------------------------------------------------------------------------------------


class FakeTelegram:
    def __init__(self, fail_send=False):
        self.sent, self.edits, self.answers, self.downloads = [], [], [], []
        self.fail_send = fail_send

    async def send_message(self, chat_id, text, reply_markup=None):
        if self.fail_send:
            raise RuntimeError("telegram down")
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return {"message_id": 99}

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text})
        return {}

    async def answer_callback_query(self, callback_query_id, text=None):
        self.answers.append({"id": callback_query_id, "text": text})
        return True

    async def download_file(self, file_id):
        self.downloads.append(file_id)
        return b"AUDIO"


class FakeTranscriber:
    def __init__(self, text="gastei 35 no almoço", exc=None):
        self.text, self.exc, self.calls = text, exc, []

    async def transcribe(self, audio, filename="audio.ogg"):
        self.calls.append({"audio": audio, "filename": filename})
        if self.exc:
            raise self.exc
        return self.text


class FakeRouter:
    def __init__(self, intencao=Intencao.ESCRITA, exc=None):
        self.intencao, self.exc, self.calls = intencao, exc, []

    async def route(self, texto):
        self.calls.append(texto)
        if self.exc:
            raise self.exc
        return Rota(self.intencao, 0.9, origem="jev")


class FakeExtractor:
    def __init__(self, result=None, exc=None):
        self.result = result or ResultadoExtracao(pagamento=pagamento())
        self.exc, self.calls = exc, []

    async def extract(self, texto, recebido_em):
        self.calls.append({"texto": texto, "recebido_em": recebido_em})
        if self.exc:
            raise self.exc
        return self.result


class FakeReadAgent:
    def __init__(self, answer="💰 Total: R$ 10,00", exc=None):
        self.answer_text, self.exc, self.calls = answer, exc, []

    async def answer(self, pergunta, agora):
        self.calls.append({"pergunta": pergunta, "agora": agora})
        if self.exc:
            raise self.exc
        return self.answer_text


class FakeStore:
    def __init__(self):
        self.items = {}

    def save(self, chat_id, user_id, expense):
        pending_id = f"id{len(self.items) + 1}"
        self.items[pending_id] = PendingExpense(pending_id, chat_id, user_id, expense, 0.0)
        return pending_id

    def get(self, pending_id):
        return self.items.get(pending_id)

    def delete(self, pending_id):
        return self.items.pop(pending_id, None) is not None


class FakeWriter:
    def __init__(self, result=True, exc=None):
        self.result, self.exc, self.calls = result, exc, []

    def append_pagamento(self, pagamento, usuario, registrado_em, id_gasto):
        self.calls.append(
            {"pagamento": pagamento, "usuario": usuario, "em": registrado_em, "id": id_gasto}
        )
        if self.exc:
            raise self.exc
        return self.result


def make_bot(allowed=frozenset({OWNER}), **overrides):
    deps = dict(
        telegram=FakeTelegram(),
        transcriber=FakeTranscriber(),
        router=FakeRouter(),
        extractor=FakeExtractor(),
        read_agent=FakeReadAgent(),
        store=FakeStore(),
        writer=FakeWriter(),
    )
    deps.update(overrides)
    bot = BotService(
        **deps, allowed_user_ids=set(allowed), timezone="America/Sao_Paulo", clock=lambda: NOW
    )
    return bot, deps


def text_update(text, user_id=OWNER, with_date=True):
    message = {
        "message_id": 10,
        "from": {"id": user_id, "first_name": "Vini"},
        "chat": {"id": user_id},
        "text": text,
    }
    if with_date:
        message["date"] = MSG_TS
    return {"update_id": 1, "message": message}


def voice_update(kind="voice"):
    media = {"file_id": "F1", "duration": 3}
    if kind == "audio":
        media["file_name"] = "nota.mp3"
    return {
        "update_id": 2,
        "message": {
            "message_id": 11,
            "date": MSG_TS,
            "from": {"id": OWNER, "first_name": "Vini"},
            "chat": {"id": OWNER},
            kind: media,
        },
    }


def callback_update(data, user_id=OWNER, sender=None):
    return {
        "update_id": 3,
        "callback_query": {
            "id": "cb1",
            "from": sender or {"id": user_id, "first_name": "Vini", "last_name": "Victor"},
            "message": {"message_id": 20, "chat": {"id": OWNER}},
            "data": data,
        },
    }


# --- autorização e comandos ---------------------------------------------------------------------


async def test_unauthorized():
    bot, d = make_bot()
    await bot.handle_update(text_update("gastei 10", user_id=999))
    assert d["telegram"].sent == [
        {"chat_id": 999, "text": M.MSG_UNAUTHORIZED.format(user_id=999), "reply_markup": None}
    ]
    assert d["router"].calls == []


async def test_empty_allowlist_denies_everyone():
    bot, d = make_bot(allowed=frozenset())
    await bot.handle_update(text_update("gastei 10"))
    assert d["telegram"].sent[0]["text"] == M.MSG_UNAUTHORIZED.format(user_id=OWNER)


@pytest.mark.parametrize("command", ["/start", "/help", "/help@MeuBot"])
async def test_help(command):
    bot, d = make_bot()
    await bot.handle_update(text_update(command))
    assert d["telegram"].sent[0]["text"] == M.MSG_HELP
    assert d["router"].calls == []


# --- escrita ------------------------------------------------------------------------------------


async def test_write_flow_asks_confirmation_with_message_timestamp():
    bot, d = make_bot()
    await bot.handle_update(text_update("almoço 35 pix"))
    assert d["router"].calls == ["almoço 35 pix"]
    call = d["extractor"].calls[0]
    assert call["texto"] == "almoço 35 pix"
    assert call["recebido_em"] == datetime(2026, 10, 9, 0, 0, tzinfo=ZoneInfo("UTC"))
    stored = d["store"].items["id1"]
    assert (stored.chat_id, stored.user_id, stored.expense) == (OWNER, OWNER, pagamento())
    assert d["telegram"].sent == [
        {
            "chat_id": OWNER,
            "text": format_confirmacao(pagamento()),
            "reply_markup": confirmation_keyboard("id1"),
        }
    ]


async def test_missing_message_date_uses_clock():
    bot, d = make_bot()
    await bot.handle_update(text_update("almoço 35", with_date=False))
    assert d["extractor"].calls[0]["recebido_em"] == NOW


async def test_write_flow_question():
    bot, d = make_bot(extractor=FakeExtractor(ResultadoExtracao(pergunta=M.MSG_PERGUNTA_VALOR)))
    await bot.handle_update(text_update("paguei o táxi"))
    assert d["telegram"].sent[0]["text"] == M.MSG_PERGUNTA_VALOR
    assert d["store"].items == {}


async def test_write_flow_not_payment():
    bot, d = make_bot(extractor=FakeExtractor(ResultadoExtracao(erro="Não é gasto.")))
    await bot.handle_update(text_update("oi"))
    assert d["telegram"].sent[0]["text"] == M.MSG_NOT_EXPENSE.format(reason="Não é gasto.")


async def test_write_flow_extraction_error():
    bot, d = make_bot(extractor=FakeExtractor(exc=ExtractionError("down")))
    await bot.handle_update(text_update("almoço 35"))
    assert d["telegram"].sent[0]["text"] == M.MSG_EXTRACTION_FAILED


# --- leitura e outro ----------------------------------------------------------------------------


async def test_read_flow():
    bot, d = make_bot(router=FakeRouter(Intencao.LEITURA))
    await bot.handle_update(text_update("quanto gastei?"))
    assert d["read_agent"].calls[0]["pergunta"] == "quanto gastei?"
    assert d["read_agent"].calls[0]["agora"] == datetime(2026, 10, 9, tzinfo=ZoneInfo("UTC"))
    assert d["telegram"].sent[0]["text"] == "💰 Total: R$ 10,00"
    assert d["extractor"].calls == []


async def test_read_flow_error():
    bot, d = make_bot(
        router=FakeRouter(Intencao.LEITURA), read_agent=FakeReadAgent(exc=ReadError("x"))
    )
    await bot.handle_update(text_update("quanto gastei?"))
    assert d["telegram"].sent[0]["text"] == M.MSG_LEITURA_FAILED


async def test_outro():
    bot, d = make_bot(router=FakeRouter(Intencao.OUTRO))
    await bot.handle_update(text_update("hmm"))
    assert d["telegram"].sent[0]["text"] == M.MSG_OUTRO
    assert d["extractor"].calls == [] and d["read_agent"].calls == []


async def test_router_error():
    bot, d = make_bot(router=FakeRouter(exc=RouterError("down")))
    await bot.handle_update(text_update("almoço 35"))
    assert d["telegram"].sent[0]["text"] == M.MSG_ROUTER_FAILED


# --- voz ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["voice", "audio"])
async def test_voice_flow(kind):
    bot, d = make_bot(transcriber=FakeTranscriber(text="almoço <35>"))
    await bot.handle_update(voice_update(kind))
    assert d["telegram"].downloads == ["F1"]
    assert d["transcriber"].calls[0]["filename"] == ("voice.ogg" if kind == "voice" else "nota.mp3")
    assert d["telegram"].sent[0]["text"] == M.MSG_TRANSCRIPTION.format(text="almoço &lt;35&gt;")
    assert d["router"].calls == ["almoço <35>"]
    assert d["telegram"].sent[1]["reply_markup"] == confirmation_keyboard("id1")


async def test_voice_failure():
    bot, d = make_bot(transcriber=FakeTranscriber(exc=TranscriptionError("x")))
    await bot.handle_update(voice_update())
    assert d["telegram"].sent[0]["text"] == M.MSG_TRANSCRIPTION_FAILED
    assert d["router"].calls == []


# --- callbacks ----------------------------------------------------------------------------------


@pytest.mark.parametrize("result", [True, False])
async def test_confirm_writes_with_pending_id(result):
    bot, d = make_bot(writer=FakeWriter(result=result))
    pending_id = d["store"].save(OWNER, OWNER, pagamento())
    await bot.handle_update(callback_update(f"confirm:{pending_id}"))
    assert d["writer"].calls == [
        {"pagamento": pagamento(), "usuario": "Vini Victor", "em": NOW, "id": pending_id}
    ]
    assert d["store"].get(pending_id) is None
    assert d["telegram"].edits == [
        {"chat_id": OWNER, "message_id": 20, "text": format_registrado(pagamento())}
    ]
    assert d["telegram"].answers == [{"id": "cb1", "text": M.MSG_CALLBACK_SAVED}]


async def test_confirm_expired():
    bot, d = make_bot()
    await bot.handle_update(callback_update("confirm:nope"))
    assert d["writer"].calls == []
    assert d["telegram"].answers == [{"id": "cb1", "text": M.MSG_EXPIRED}]
    assert d["telegram"].edits[0]["text"] == M.MSG_EXPIRED


async def test_confirm_by_other_user():
    bot, d = make_bot(allowed=frozenset({OWNER, 222}))
    pending_id = d["store"].save(OWNER, OWNER, pagamento())
    await bot.handle_update(callback_update(f"confirm:{pending_id}", user_id=222))
    assert d["writer"].calls == []
    assert d["telegram"].answers == [{"id": "cb1", "text": M.MSG_NOT_OWNER}]


async def test_sheet_failure_keeps_pending():
    bot, d = make_bot(writer=FakeWriter(exc=SheetsError("down")))
    pending_id = d["store"].save(OWNER, OWNER, pagamento())
    await bot.handle_update(callback_update(f"confirm:{pending_id}"))
    assert d["store"].get(pending_id) is not None
    assert d["telegram"].answers == [{"id": "cb1", "text": M.MSG_SAVE_FAILED}]
    assert d["telegram"].edits == []


async def test_cancel():
    bot, d = make_bot()
    pending_id = d["store"].save(OWNER, OWNER, pagamento())
    await bot.handle_update(callback_update(f"cancel:{pending_id}"))
    assert d["store"].get(pending_id) is None
    assert d["telegram"].edits[0]["text"] == M.MSG_CANCELLED
    assert d["telegram"].answers == [{"id": "cb1", "text": M.MSG_CALLBACK_CANCELLED}]


async def test_unknown_callback_and_user_name_fallback():
    bot, d = make_bot()
    await bot.handle_update(callback_update("whatever"))
    assert len(d["telegram"].answers) == 1
    pending_id = d["store"].save(OWNER, OWNER, pagamento())
    await bot.handle_update(
        callback_update(f"confirm:{pending_id}", sender={"id": OWNER, "username": "vini"})
    )
    assert d["writer"].calls[0]["usuario"] == "vini"


@pytest.mark.parametrize(
    "update",
    [
        {"update_id": 5},
        {"update_id": 6, "edited_message": {"message_id": 1, "chat": {"id": 1}}},
        {
            "update_id": 7,
            "message": {
                "message_id": 1,
                "from": {"id": OWNER},
                "chat": {"id": OWNER},
                "sticker": {},
            },
        },
    ],
)
async def test_unsupported_updates(update):
    bot, d = make_bot()
    await bot.handle_update(update)
    assert d["router"].calls == [] and d["telegram"].sent == []


async def test_never_raises():
    bot, _ = make_bot(telegram=FakeTelegram(fail_send=True))
    await bot.handle_update(text_update("almoço 35"))
