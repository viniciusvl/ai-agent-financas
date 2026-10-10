"""Testes unitários dos callbacks do BotService (T16, sessão 3)."""

from datetime import UTC, date, datetime, time
from decimal import Decimal

from app import messages as M
from app.bot import BotService
from app.payment import Pagamento
from app.pending_store import PendingExpense

NOW = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
OWNER = 111


def pagamento():
    return Pagamento(
        metodo_pagamento="pix",
        data=date(2026, 10, 9),
        hora=time(14, 7),
        valor_compra=Decimal("35"),
        moeda="BRL",
        categoria="alimentação",
        descricao="almoço",
    )


class FakeTelegram:
    def __init__(self):
        self.edits, self.answers = [], []

    async def send_message(self, chat_id, text, reply_markup=None):
        return {"message_id": 1}

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text})

    async def answer_callback_query(self, callback_query_id, text=None):
        self.answers.append({"id": callback_query_id, "text": text})


class FakeStore:
    def __init__(self):
        self.items = {}

    def save(self, chat_id, user_id, expense):
        pid = f"id{len(self.items) + 1}"
        self.items[pid] = PendingExpense(pid, chat_id, user_id, expense, 0.0)
        return pid

    def get(self, pending_id):
        return self.items.get(pending_id)

    def delete(self, pending_id):
        return self.items.pop(pending_id, None) is not None


class FakeWriter:
    def __init__(self):
        self.calls = []

    def append_pagamento(self, pagamento, usuario, registrado_em, id_gasto):
        self.calls.append(usuario)
        return True


def make_bot(allowed=frozenset({OWNER})):
    telegram = FakeTelegram()
    store = FakeStore()
    writer = FakeWriter()
    bot = BotService(
        telegram=telegram,
        transcriber=None,
        router=None,
        extractor=None,
        read_agent=None,
        store=store,
        writer=writer,
        allowed_user_ids=set(allowed),
        timezone="UTC",
        clock=lambda: NOW,
    )
    return bot, telegram, store, writer


def callback_update(data, sender=None):
    return {
        "update_id": 3,
        "callback_query": {
            "id": "cb1",
            "from": sender or {"id": OWNER, "first_name": "Vini", "last_name": "Victor"},
            "message": {"message_id": 20, "chat": {"id": OWNER}},
            "data": data,
        },
    }


async def test_callback_nao_autorizado():
    bot, telegram, _, _ = make_bot()
    await bot.handle_update(callback_update("confirm:id1", sender={"id": 999}))
    assert telegram.answers == [{"id": "cb1", "text": M.MSG_UNAUTHORIZED.format(user_id=999)}]
    assert telegram.edits == []


async def test_cancel_por_outro_usuario_nao_apaga():
    bot, telegram, store, _ = make_bot(allowed=frozenset({OWNER, 222}))
    pid = store.save(OWNER, OWNER, pagamento())
    await bot.handle_update(
        callback_update(f"cancel:{pid}", sender={"id": 222, "first_name": "Outro"})
    )
    assert store.get(pid) is not None
    assert telegram.answers == [{"id": "cb1", "text": M.MSG_NOT_OWNER}]
    assert telegram.edits == []


async def test_cancel_expirado():
    bot, telegram, _, _ = make_bot()
    await bot.handle_update(callback_update("cancel:nope"))
    assert telegram.answers == [{"id": "cb1", "text": M.MSG_EXPIRED}]
    assert telegram.edits == [{"chat_id": OWNER, "message_id": 20, "text": M.MSG_EXPIRED}]


async def test_user_name_usa_id_quando_sem_nome():
    bot, _, store, writer = make_bot()
    pid = store.save(OWNER, OWNER, pagamento())
    await bot.handle_update(callback_update(f"confirm:{pid}", sender={"id": OWNER}))
    assert writer.calls == [str(OWNER)]
