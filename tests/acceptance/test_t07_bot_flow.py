from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app import messages as M
from app.bot import BotService
from app.domain import Expense, format_confirmation
from app.extractor import ExtractionError, ExtractionResult
from app.pending_store import PendingExpense
from app.sheets import SheetsError
from app.stt import TranscriptionError
from app.telegram_api import confirmation_keyboard

pytestmark = pytest.mark.task("T07")

NOW = datetime(2026, 10, 8, 23, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
OWNER = 111


def expense(**kw):
    data = dict(amount=Decimal("35"), description="almoço", spent_at=date(2026, 10, 8))
    data.update(kw)
    return Expense(**data)


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


class FakeExtractor:
    def __init__(self, result=None, exc=None):
        self.result = result or ExtractionResult(expense=expense())
        self.exc, self.calls = exc, []

    async def extract(self, text, today):
        self.calls.append({"text": text, "today": today})
        if self.exc:
            raise self.exc
        return self.result


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


class FakeSheets:
    def __init__(self, exc=None):
        self.exc, self.appended = exc, []

    def append_expense(self, expense, user, recorded_at):
        if self.exc:
            raise self.exc
        self.appended.append({"expense": expense, "user": user, "recorded_at": recorded_at})


def make_bot(**overrides):
    deps = dict(
        telegram=FakeTelegram(),
        transcriber=FakeTranscriber(),
        extractor=FakeExtractor(),
        store=FakeStore(),
        sheets=FakeSheets(),
    )
    deps.update(overrides)
    bot = BotService(
        **deps,
        allowed_user_ids={OWNER},
        timezone="Asia/Shanghai",
        clock=lambda: NOW,
    )
    return bot, deps


def text_update(text, user_id=OWNER, **from_extra):
    sender = {"id": user_id, "first_name": "Vini", **from_extra}
    return {
        "update_id": 1,
        "message": {"message_id": 10, "from": sender, "chat": {"id": user_id}, "text": text},
    }


def voice_update(kind="voice"):
    media = {"file_id": "F1", "duration": 3}
    if kind == "audio":
        media["file_name"] = "nota.mp3"
    return {
        "update_id": 2,
        "message": {
            "message_id": 11,
            "from": {"id": OWNER, "first_name": "Vini"},
            "chat": {"id": OWNER},
            kind: media,
        },
    }


def callback_update(data, user_id=OWNER):
    return {
        "update_id": 3,
        "callback_query": {
            "id": "cb1",
            "from": {"id": user_id, "first_name": "Vini", "last_name": "Victor"},
            "message": {"message_id": 20, "chat": {"id": OWNER}},
            "data": data,
        },
    }


async def test_unauthorized_user_gets_id_and_nothing_else():
    bot, d = make_bot()
    await bot.handle_update(text_update("gastei 10", user_id=999))
    assert d["telegram"].sent == [
        {"chat_id": 999, "text": M.MSG_UNAUTHORIZED.format(user_id=999), "reply_markup": None}
    ]
    assert d["extractor"].calls == []


async def test_empty_allowlist_denies_everyone():
    deps = dict(
        telegram=FakeTelegram(),
        transcriber=FakeTranscriber(),
        extractor=FakeExtractor(),
        store=FakeStore(),
        sheets=FakeSheets(),
    )
    bot = BotService(**deps, allowed_user_ids=set(), clock=lambda: NOW)
    await bot.handle_update(text_update("gastei 10"))
    assert deps["telegram"].sent[0]["text"] == M.MSG_UNAUTHORIZED.format(user_id=OWNER)
    assert deps["extractor"].calls == []


@pytest.mark.parametrize("command", ["/start", "/help", "/start@MeuBot"])
async def test_help_commands(command):
    bot, d = make_bot()
    await bot.handle_update(text_update(command))
    assert d["telegram"].sent[0]["text"] == M.MSG_HELP
    assert d["extractor"].calls == []


async def test_text_expense_asks_confirmation():
    bot, d = make_bot()
    await bot.handle_update(text_update("gastei 35 no almoço"))
    assert d["extractor"].calls == [{"text": "gastei 35 no almoço", "today": date(2026, 10, 8)}]
    assert list(d["store"].items) == ["id1"]
    stored = d["store"].items["id1"]
    assert (stored.chat_id, stored.user_id, stored.expense) == (OWNER, OWNER, expense())
    assert d["telegram"].sent == [
        {
            "chat_id": OWNER,
            "text": format_confirmation(expense()),
            "reply_markup": confirmation_keyboard("id1"),
        }
    ]


async def test_today_uses_configured_timezone():
    utc_late = datetime(2026, 10, 8, 20, 0, tzinfo=ZoneInfo("UTC"))  # 04:00 do dia 9 em Xangai
    deps = dict(
        telegram=FakeTelegram(),
        transcriber=FakeTranscriber(),
        extractor=FakeExtractor(),
        store=FakeStore(),
        sheets=FakeSheets(),
    )
    bot = BotService(**deps, allowed_user_ids={OWNER}, clock=lambda: utc_late)
    await bot.handle_update(text_update("gastei 35"))
    assert deps["extractor"].calls[0]["today"] == date(2026, 10, 9)


async def test_text_not_expense():
    bot, d = make_bot(extractor=FakeExtractor(ExtractionResult(error="Isso é uma saudação.")))
    await bot.handle_update(text_update("oi"))
    assert d["telegram"].sent[0]["text"] == M.MSG_NOT_EXPENSE.format(reason="Isso é uma saudação.")
    assert d["store"].items == {}


async def test_extraction_error():
    bot, d = make_bot(extractor=FakeExtractor(exc=ExtractionError("down")))
    await bot.handle_update(text_update("gastei 35"))
    assert d["telegram"].sent[0]["text"] == M.MSG_EXTRACTION_FAILED


@pytest.mark.parametrize("kind", ["voice", "audio"])
async def test_voice_flow(kind):
    bot, d = make_bot(transcriber=FakeTranscriber(text="gastei <35> no almoço"))
    await bot.handle_update(voice_update(kind))
    assert d["telegram"].downloads == ["F1"]
    assert d["transcriber"].calls[0]["audio"] == b"AUDIO"
    expected_name = "voice.ogg" if kind == "voice" else "nota.mp3"
    assert d["transcriber"].calls[0]["filename"] == expected_name
    sent = d["telegram"].sent
    assert sent[0]["text"] == M.MSG_TRANSCRIPTION.format(text="gastei &lt;35&gt; no almoço")
    assert d["extractor"].calls[0]["text"] == "gastei <35> no almoço"
    assert sent[1]["reply_markup"] == confirmation_keyboard("id1")


async def test_transcription_failure():
    bot, d = make_bot(transcriber=FakeTranscriber(exc=TranscriptionError("x")))
    await bot.handle_update(voice_update())
    assert d["telegram"].sent[0]["text"] == M.MSG_TRANSCRIPTION_FAILED
    assert d["extractor"].calls == []


async def test_confirm_saves_to_sheet():
    bot, d = make_bot()
    pending_id = d["store"].save(OWNER, OWNER, expense())
    await bot.handle_update(callback_update(f"confirm:{pending_id}"))
    assert d["sheets"].appended == [
        {"expense": expense(), "user": "Vini Victor", "recorded_at": NOW}
    ]
    assert d["store"].get(pending_id) is None
    edit = d["telegram"].edits[0]
    assert (edit["chat_id"], edit["message_id"]) == (OWNER, 20)
    assert edit["text"].startswith(M.MSG_SAVED_HEADER)
    assert "almoço" in edit["text"]
    assert "Confirme o gasto" not in edit["text"]
    assert d["telegram"].answers == [{"id": "cb1", "text": M.MSG_CALLBACK_SAVED}]


async def test_confirm_expired():
    bot, d = make_bot()
    await bot.handle_update(callback_update("confirm:nope"))
    assert d["sheets"].appended == []
    assert d["telegram"].answers == [{"id": "cb1", "text": M.MSG_EXPIRED}]
    assert d["telegram"].edits[0]["text"] == M.MSG_EXPIRED


async def test_confirm_by_other_user_is_rejected():
    bot, d = make_bot()
    pending_id = d["store"].save(OWNER, OWNER, expense())
    bot.allowed_user_ids.add(222)
    await bot.handle_update(callback_update(f"confirm:{pending_id}", user_id=222))
    assert d["sheets"].appended == []
    assert d["store"].get(pending_id) is not None
    assert d["telegram"].answers == [{"id": "cb1", "text": M.MSG_NOT_OWNER}]


async def test_sheets_failure_keeps_pending():
    bot, d = make_bot(sheets=FakeSheets(exc=SheetsError("down")))
    pending_id = d["store"].save(OWNER, OWNER, expense())
    await bot.handle_update(callback_update(f"confirm:{pending_id}"))
    assert d["store"].get(pending_id) is not None
    assert d["telegram"].answers == [{"id": "cb1", "text": M.MSG_SAVE_FAILED}]
    assert d["telegram"].edits == []


async def test_cancel():
    bot, d = make_bot()
    pending_id = d["store"].save(OWNER, OWNER, expense())
    await bot.handle_update(callback_update(f"cancel:{pending_id}"))
    assert d["store"].get(pending_id) is None
    assert d["sheets"].appended == []
    assert d["telegram"].edits[0]["text"] == M.MSG_CANCELLED
    assert d["telegram"].answers == [{"id": "cb1", "text": M.MSG_CALLBACK_CANCELLED}]


async def test_unknown_callback_data_is_answered():
    bot, d = make_bot()
    await bot.handle_update(callback_update("whatever"))
    assert len(d["telegram"].answers) == 1
    assert d["sheets"].appended == []


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
async def test_unsupported_updates_are_ignored(update):
    bot, d = make_bot()
    await bot.handle_update(update)
    assert d["extractor"].calls == []
    assert d["sheets"].appended == []


async def test_handle_update_never_raises():
    bot, _ = make_bot(telegram=FakeTelegram(fail_send=True))
    await bot.handle_update(text_update("gastei 35"))


async def test_user_display_name_fallbacks():
    bot, d = make_bot()
    pending_id = d["store"].save(OWNER, OWNER, expense())
    update = callback_update(f"confirm:{pending_id}")
    update["callback_query"]["from"] = {"id": OWNER, "username": "vini"}
    await bot.handle_update(update)
    assert d["sheets"].appended[0]["user"] == "vini"
