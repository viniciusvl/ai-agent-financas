"""Testes unitários do núcleo do cliente da Bot API (subtarefa 1 da T02)."""

import httpx
import pytest

from app.telegram_api import TelegramClient, TelegramError, confirmation_keyboard


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeHTTP:
    """AsyncClient falso que registra chamadas e não toca na rede."""

    def __init__(self, response):
        self._response = response
        self.calls = []
        self.closed = False

    async def post(self, url, json=None):
        self.calls.append((url, json))
        if isinstance(self._response, Exception):
            raise self._response
        return FakeResponse(self._response)

    async def aclose(self):
        self.closed = True


def test_confirmation_keyboard_has_both_buttons():
    keyboard = confirmation_keyboard("abc")
    assert keyboard == {
        "inline_keyboard": [
            [
                {"text": "✅ Confirmar", "callback_data": "confirm:abc"},
                {"text": "❌ Cancelar", "callback_data": "cancel:abc"},
            ]
        ]
    }


async def test_call_returns_result_and_posts_json():
    http = FakeHTTP({"ok": True, "result": {"message_id": 1}})
    client = TelegramClient("123:ABC", http=http)

    result = await client._call("sendMessage", {"chat_id": 1})

    assert result == {"message_id": 1}
    url, payload = http.calls[0]
    assert url == "https://api.telegram.org/bot123:ABC/sendMessage"
    assert payload == {"chat_id": 1}


async def test_call_ok_false_with_200_raises_with_description():
    http = FakeHTTP({"ok": False, "description": "weird"})
    client = TelegramClient("123:ABC", http=http)

    with pytest.raises(TelegramError, match="weird"):
        await client._call("sendMessage", {})


async def test_call_without_description_raises_generic_message():
    http = FakeHTTP({"ok": False})
    client = TelegramClient("123:ABC", http=http)

    with pytest.raises(TelegramError):
        await client._call("sendMessage", {})


async def test_call_network_error_raises_telegram_error():
    http = FakeHTTP(httpx.ConnectError("boom"))
    client = TelegramClient("123:ABC", http=http)

    with pytest.raises(TelegramError):
        await client._call("sendMessage", {})


async def test_call_non_json_response_raises():
    http = FakeHTTP(ValueError("não é json"))
    client = TelegramClient("123:ABC", http=http)

    with pytest.raises(TelegramError):
        await client._call("sendMessage", {})


async def test_aclose_does_not_close_injected_http():
    http = FakeHTTP({"ok": True, "result": True})
    client = TelegramClient("123:ABC", http=http)

    await client.aclose()

    assert http.closed is False


async def test_client_creates_and_closes_own_http():
    client = TelegramClient("123:ABC")

    assert isinstance(client._http, httpx.AsyncClient)
    await client.aclose()
    assert client._http.is_closed is True


def test_base_url_trailing_slash_stripped():
    client = TelegramClient("t", http=FakeHTTP({}), base_url="https://x.test/")
    assert client.base_url == "https://x.test"
