import json

import httpx
import pytest
import respx

from app.telegram_api import TelegramClient, TelegramError, confirmation_keyboard

pytestmark = pytest.mark.task("T02")

BASE = "https://api.telegram.org"
TOKEN = "123:ABC"
API = f"{BASE}/bot{TOKEN}"


def ok(result):
    return httpx.Response(200, json={"ok": True, "result": result})


def body(route):
    return json.loads(route.calls.last.request.content)


@pytest.fixture
async def tg():
    async with httpx.AsyncClient() as http:
        yield TelegramClient(TOKEN, http=http)


def test_confirmation_keyboard():
    assert confirmation_keyboard("abc") == {
        "inline_keyboard": [
            [
                {"text": "✅ Confirmar", "callback_data": "confirm:abc"},
                {"text": "❌ Cancelar", "callback_data": "cancel:abc"},
            ]
        ]
    }


@respx.mock
async def test_send_message_with_markup(tg):
    route = respx.post(f"{API}/sendMessage").mock(return_value=ok({"message_id": 7}))
    result = await tg.send_message(42, "oi", reply_markup={"inline_keyboard": []})
    assert result == {"message_id": 7}
    assert body(route) == {
        "chat_id": 42,
        "text": "oi",
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": []},
    }


@respx.mock
async def test_send_message_without_markup_omits_key(tg):
    route = respx.post(f"{API}/sendMessage").mock(return_value=ok({"message_id": 8}))
    await tg.send_message(42, "oi")
    assert body(route) == {"chat_id": 42, "text": "oi", "parse_mode": "HTML"}


@respx.mock
async def test_api_error_raises_telegram_error(tg):
    respx.post(f"{API}/sendMessage").mock(
        return_value=httpx.Response(
            400, json={"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}
        )
    )
    with pytest.raises(TelegramError, match="chat not found"):
        await tg.send_message(42, "oi")


@respx.mock
async def test_ok_false_with_200_raises(tg):
    respx.post(f"{API}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": False, "description": "weird"})
    )
    with pytest.raises(TelegramError, match="weird"):
        await tg.send_message(42, "oi")


@respx.mock
async def test_network_error_raises_telegram_error(tg):
    respx.post(f"{API}/sendMessage").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(TelegramError):
        await tg.send_message(42, "oi")


@respx.mock
async def test_edit_message_text(tg):
    route = respx.post(f"{API}/editMessageText").mock(return_value=ok({"message_id": 20}))
    await tg.edit_message_text(42, 20, "novo")
    assert body(route) == {"chat_id": 42, "message_id": 20, "text": "novo", "parse_mode": "HTML"}
    await tg.edit_message_text(42, 20, "novo", reply_markup={"inline_keyboard": []})
    assert body(route)["reply_markup"] == {"inline_keyboard": []}


@respx.mock
async def test_answer_callback_query(tg):
    route = respx.post(f"{API}/answerCallbackQuery").mock(return_value=ok(True))
    assert await tg.answer_callback_query("cb1") is True
    assert body(route) == {"callback_query_id": "cb1"}
    await tg.answer_callback_query("cb1", text="Registrado!")
    assert body(route) == {"callback_query_id": "cb1", "text": "Registrado!"}


@respx.mock
async def test_download_file(tg):
    get_file = respx.post(f"{API}/getFile").mock(
        return_value=ok({"file_id": "F1", "file_path": "voice/file_1.oga"})
    )
    respx.get(f"{BASE}/file/bot{TOKEN}/voice/file_1.oga").mock(
        return_value=httpx.Response(200, content=b"OGGDATA")
    )
    assert await tg.download_file("F1") == b"OGGDATA"
    assert body(get_file) == {"file_id": "F1"}


@respx.mock
async def test_download_file_http_error(tg):
    respx.post(f"{API}/getFile").mock(return_value=ok({"file_path": "voice/x.oga"}))
    respx.get(f"{BASE}/file/bot{TOKEN}/voice/x.oga").mock(return_value=httpx.Response(404))
    with pytest.raises(TelegramError):
        await tg.download_file("F1")


@respx.mock
async def test_set_webhook(tg):
    route = respx.post(f"{API}/setWebhook").mock(return_value=ok(True))
    assert await tg.set_webhook("https://bot.example.com/telegram/webhook", "s3cr3t") is True
    assert body(route) == {
        "url": "https://bot.example.com/telegram/webhook",
        "secret_token": "s3cr3t",
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": False,
    }


@respx.mock
async def test_client_without_injected_http():
    route = respx.post(f"{API}/sendMessage").mock(return_value=ok({"message_id": 1}))
    client = TelegramClient(TOKEN)
    try:
        await client.send_message(1, "x")
    finally:
        await client.aclose()
    assert route.called
