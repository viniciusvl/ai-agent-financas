"""Testes unitários da memória de ids confirmados (T20)."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from app.bot import CONFIRMADOS_TTL, BotService
from app.messages import MSG_EXPIRED
from app.payment import Pagamento
from app.pending_store import PendingExpense

OWNER = 111


def pagamento() -> Pagamento:
    return Pagamento(
        metodo_pagamento="pix",
        data=date(2026, 10, 9),
        hora=time(14, 7),
        valor_compra=Decimal("35"),
        moeda="BRL",
        categoria="alimentação",
        descricao="almoço",
    )


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class FakeTelegram:
    def __init__(self) -> None:
        self.edits: list[dict] = []
        self.answers: list[dict] = []

    async def send_message(self, chat_id, text, reply_markup=None):
        return {"message_id": 1}

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text})

    async def answer_callback_query(self, callback_query_id, text=None):
        self.answers.append({"id": callback_query_id, "text": text})


class FakeStore:
    def __init__(self) -> None:
        self.items: dict[str, PendingExpense] = {}

    def save(self, chat_id, user_id, expense):
        pid = f"id{len(self.items) + 1}"
        self.items[pid] = PendingExpense(pid, chat_id, user_id, expense, 0.0)
        return pid

    def get(self, pending_id):
        return self.items.get(pending_id)

    def delete(self, pending_id):
        return self.items.pop(pending_id, None) is not None


class FakeWriter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def append_pagamento(self, pagamento, usuario, registrado_em, id_gasto):
        self.calls.append({"id": id_gasto})
        return True


def make_bot():
    telegram = FakeTelegram()
    store = FakeStore()
    clock = Clock()
    bot = BotService(
        telegram=telegram,
        transcriber=None,
        router=None,
        extractor=None,
        read_agent=None,
        store=store,
        writer=FakeWriter(),
        allowed_user_ids={OWNER},
        timezone="UTC",
        clock=clock,
    )
    return bot, telegram, store, clock


def callback_update(data):
    return {
        "update_id": 3,
        "callback_query": {
            "id": "cb1",
            "from": {"id": OWNER, "first_name": "Vini"},
            "message": {"message_id": 20, "chat": {"id": OWNER}},
            "data": data,
        },
    }


async def test_confirmados_vencem_e_sao_purgados():
    bot, telegram, store, clock = make_bot()
    pid = store.save(OWNER, OWNER, pagamento())
    await bot.handle_update(callback_update(f"confirm:{pid}"))
    assert bot._confirmados == {pid: clock.now}

    clock.now += CONFIRMADOS_TTL
    assert bot._ja_confirmado(pid) is True

    clock.now += timedelta(seconds=1)
    assert bot._ja_confirmado(pid) is False
    assert bot._confirmados == {}


async def test_cancel_nao_grava_na_memoria():
    bot, _, store, _ = make_bot()
    pid = store.save(OWNER, OWNER, pagamento())
    await bot.handle_update(callback_update(f"cancel:{pid}"))
    assert bot._confirmados == {}


async def test_toque_duplo_em_cancel_continua_expirado():
    bot, telegram, store, _ = make_bot()
    pid = store.save(OWNER, OWNER, pagamento())
    await bot.handle_update(callback_update(f"cancel:{pid}"))
    await bot.handle_update(callback_update(f"cancel:{pid}"))
    assert telegram.answers[-1] == {"id": "cb1", "text": MSG_EXPIRED}
    assert telegram.edits[-1]["text"] == MSG_EXPIRED
