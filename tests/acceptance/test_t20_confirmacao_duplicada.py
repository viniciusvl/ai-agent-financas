from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app import messages as M
from app.bot import BotService, format_registrado
from tests.acceptance.test_t16_bot_flow_v2 import (
    OWNER,
    FakeExtractor,
    FakeReadAgent,
    FakeRouter,
    FakeStore,
    FakeTelegram,
    FakeTranscriber,
    FakeWriter,
    callback_update,
    pagamento,
)

pytestmark = pytest.mark.task("T20")


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 9, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

    def __call__(self):
        return self.now


def make_bot():
    deps = dict(
        telegram=FakeTelegram(),
        transcriber=FakeTranscriber(),
        router=FakeRouter(),
        extractor=FakeExtractor(),
        read_agent=FakeReadAgent(),
        store=FakeStore(),
        writer=FakeWriter(),
    )
    clock = Clock()
    bot = BotService(**deps, allowed_user_ids={OWNER}, timezone="America/Sao_Paulo", clock=clock)
    return bot, deps, clock


async def test_toque_duplo_nao_mostra_expirado():
    bot, d, _ = make_bot()
    pending_id = d["store"].save(OWNER, OWNER, pagamento())
    await bot.handle_update(callback_update(f"confirm:{pending_id}"))
    await bot.handle_update(callback_update(f"confirm:{pending_id}"))
    assert len(d["writer"].calls) == 1
    assert d["telegram"].edits == [
        {"chat_id": OWNER, "message_id": 20, "text": format_registrado(pagamento())}
    ]
    assert d["telegram"].answers == [
        {"id": "cb1", "text": M.MSG_CALLBACK_SAVED},
        {"id": "cb1", "text": M.MSG_CALLBACK_SAVED},
    ]


async def test_memoria_vence_em_10_minutos():
    bot, d, clock = make_bot()
    pending_id = d["store"].save(OWNER, OWNER, pagamento())
    await bot.handle_update(callback_update(f"confirm:{pending_id}"))
    clock.now += timedelta(minutes=10, seconds=1)
    await bot.handle_update(callback_update(f"confirm:{pending_id}"))
    assert d["telegram"].answers[-1] == {"id": "cb1", "text": M.MSG_EXPIRED}
    assert d["telegram"].edits[-1]["text"] == M.MSG_EXPIRED


async def test_id_nunca_confirmado_continua_expirado():
    bot, d, _ = make_bot()
    await bot.handle_update(callback_update("confirm:desconhecido"))
    assert d["telegram"].answers == [{"id": "cb1", "text": M.MSG_EXPIRED}]
    assert d["telegram"].edits[0]["text"] == M.MSG_EXPIRED


async def test_falha_na_planilha_nao_marca_como_confirmado():
    from app.sheets import SheetsError

    bot, d, _ = make_bot()
    bot.writer = FakeWriter(exc=SheetsError("down"))
    pending_id = d["store"].save(OWNER, OWNER, pagamento())
    await bot.handle_update(callback_update(f"confirm:{pending_id}"))
    d["store"].delete(pending_id)
    await bot.handle_update(callback_update(f"confirm:{pending_id}"))
    assert d["telegram"].answers[-1] == {"id": "cb1", "text": M.MSG_EXPIRED}
