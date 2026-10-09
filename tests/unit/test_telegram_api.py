import httpx
import pytest
import respx

from app.telegram_api import TelegramClient, TelegramError, confirmation_keyboard

BASE = "https://api.telegram.org"
TOKEN = "123:ABC"
API = f"{BASE}/bot{TOKEN}"


def test_confirmation_keyboard_uses_pending_id():
    assert confirmation_keyboard("abc")["inline_keyboard"][0] == [
        {"text": "✅ Confirmar", "callback_data": "confirm:abc"},
        {"text": "❌ Cancelar", "callback_data": "cancel:abc"},
    ]


@respx.mock
async def test_call_returns_result():
    respx.post(f"{API}/getMe").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": 1})
    )
    async with httpx.AsyncClient() as http:
        client = TelegramClient(TOKEN, http=http)
        assert await client._call("getMe", {}) == 1


@respx.mock
async def test_call_api_error_includes_description():
    respx.post(f"{API}/getMe").mock(
        return_value=httpx.Response(400, json={"ok": False, "description": "nope"})
    )
    async with httpx.AsyncClient() as http:
        client = TelegramClient(TOKEN, http=http)
        with pytest.raises(TelegramError, match="nope"):
            await client._call("getMe", {})


@respx.mock
async def test_call_network_error_raises():
    respx.post(f"{API}/getMe").mock(side_effect=httpx.ConnectError("boom"))
    async with httpx.AsyncClient() as http:
        client = TelegramClient(TOKEN, http=http)
        with pytest.raises(TelegramError):
            await client._call("getMe", {})


@respx.mock
async def test_call_non_json_response_raises():
    respx.post(f"{API}/getMe").mock(return_value=httpx.Response(500, text="<html/>"))
    async with httpx.AsyncClient() as http:
        client = TelegramClient(TOKEN, http=http)
        with pytest.raises(TelegramError):
            await client._call("getMe", {})


async def test_aclose_does_not_close_injected_client():
    async with httpx.AsyncClient() as http:
        client = TelegramClient(TOKEN, http=http)
        await client.aclose()
        assert http.is_closed is False


async def test_aclose_closes_own_client():
    client = TelegramClient(TOKEN)
    await client.aclose()
    assert client._http.is_closed is True
