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


async def test_send_message_includes_markup_when_given():
    http = FakeHTTP({"ok": True, "result": {"message_id": 7}})
    client = TelegramClient("123:ABC", http=http)

    result = await client.send_message(42, "oi", reply_markup={"inline_keyboard": []})

    assert result == {"message_id": 7}
    _, payload = http.calls[0]
    assert payload == {
        "chat_id": 42,
        "text": "oi",
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": []},
    }


async def test_send_message_omits_markup_when_absent():
    http = FakeHTTP({"ok": True, "result": {"message_id": 8}})
    client = TelegramClient("123:ABC", http=http)

    await client.send_message(42, "oi")

    _, payload = http.calls[0]
    assert payload == {"chat_id": 42, "text": "oi", "parse_mode": "HTML"}


async def test_edit_message_text_payload_and_markup():
    http = FakeHTTP({"ok": True, "result": {"message_id": 20}})
    client = TelegramClient("123:ABC", http=http)

    await client.edit_message_text(42, 20, "novo")
    assert http.calls[0][1] == {
        "chat_id": 42,
        "message_id": 20,
        "text": "novo",
        "parse_mode": "HTML",
    }

    await client.edit_message_text(42, 20, "novo", reply_markup={"inline_keyboard": []})
    assert http.calls[1][1]["reply_markup"] == {"inline_keyboard": []}


async def test_answer_callback_query_returns_true_and_optional_text():
    http = FakeHTTP({"ok": True, "result": True})
    client = TelegramClient("123:ABC", http=http)

    assert await client.answer_callback_query("cb1") is True
    assert http.calls[0][1] == {"callback_query_id": "cb1"}

    await client.answer_callback_query("cb1", text="Registrado!")
    assert http.calls[1][1] == {"callback_query_id": "cb1", "text": "Registrado!"}


async def test_set_webhook_payload_and_true():
    http = FakeHTTP({"ok": True, "result": True})
    client = TelegramClient("123:ABC", http=http)

    assert await client.set_webhook("https://bot.example.com/hook", "s3cr3t") is True
    assert http.calls[0][1] == {
        "url": "https://bot.example.com/hook",
        "secret_token": "s3cr3t",
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": False,
    }


class FakeDownloadResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content
        self.is_success = 200 <= status_code < 300


class FakeDownloadHTTP(FakeHTTP):
    """FakeHTTP com suporte a GET para exercitar ``download_file``."""

    def __init__(self, response, get_response):
        super().__init__(response)
        self._get_response = get_response
        self.get_calls = []

    async def get(self, url):
        self.get_calls.append(url)
        if isinstance(self._get_response, Exception):
            raise self._get_response
        return self._get_response


async def test_download_file_returns_content_and_calls_getfile():
    http = FakeDownloadHTTP(
        {"ok": True, "result": {"file_id": "F1", "file_path": "voice/file_1.oga"}},
        FakeDownloadResponse(200, b"OGGDATA"),
    )
    client = TelegramClient("123:ABC", http=http)

    assert await client.download_file("F1") == b"OGGDATA"
    assert http.calls[0][0] == "https://api.telegram.org/bot123:ABC/getFile"
    assert http.calls[0][1] == {"file_id": "F1"}
    assert http.get_calls == ["https://api.telegram.org/file/bot123:ABC/voice/file_1.oga"]


async def test_download_file_non_2xx_raises_telegram_error():
    http = FakeDownloadHTTP(
        {"ok": True, "result": {"file_path": "voice/x.oga"}},
        FakeDownloadResponse(404),
    )
    client = TelegramClient("123:ABC", http=http)

    with pytest.raises(TelegramError):
        await client.download_file("F1")


async def test_download_file_network_error_raises_telegram_error():
    http = FakeDownloadHTTP(
        {"ok": True, "result": {"file_path": "voice/x.oga"}},
        httpx.ConnectError("boom"),
    )
    client = TelegramClient("123:ABC", http=http)

    with pytest.raises(TelegramError):
        await client.download_file("F1")
