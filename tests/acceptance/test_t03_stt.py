from types import SimpleNamespace

import pytest

from app.stt import TranscriptionError, WhisperTranscriber

pytestmark = pytest.mark.task("T03")


class FakeTranscriptions:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.result


def fake_client(result=None, exc=None):
    return SimpleNamespace(audio=SimpleNamespace(transcriptions=FakeTranscriptions(result, exc)))


async def test_transcribe_returns_stripped_text():
    client = fake_client("  gastei 35 reais no almoço \n")
    stt = WhisperTranscriber(api_key="k", client=client)
    assert await stt.transcribe(b"data", filename="voice.ogg") == "gastei 35 reais no almoço"
    call = client.audio.transcriptions.calls[0]
    assert call["model"] == "whisper-1"
    assert call["language"] == "pt"
    assert call["response_format"] == "text"
    assert call["file"] == ("voice.ogg", b"data")


async def test_oga_extension_is_renamed_to_ogg():
    client = fake_client("ok")
    stt = WhisperTranscriber(api_key="k", client=client)
    await stt.transcribe(b"data", filename="file_1.oga")
    assert client.audio.transcriptions.calls[0]["file"] == ("file_1.ogg", b"data")


async def test_custom_model_and_language():
    client = fake_client("ok")
    stt = WhisperTranscriber(api_key="k", model="large-v3", language="en", client=client)
    await stt.transcribe(b"data")
    call = client.audio.transcriptions.calls[0]
    assert call["model"] == "large-v3"
    assert call["language"] == "en"


async def test_object_with_text_attribute_is_supported():
    client = fake_client(SimpleNamespace(text=" olá "))
    stt = WhisperTranscriber(api_key="k", client=client)
    assert await stt.transcribe(b"data") == "olá"


async def test_empty_transcription_raises():
    stt = WhisperTranscriber(api_key="k", client=fake_client("   "))
    with pytest.raises(TranscriptionError):
        await stt.transcribe(b"data")


async def test_empty_audio_raises_without_calling_api():
    client = fake_client("x")
    stt = WhisperTranscriber(api_key="k", client=client)
    with pytest.raises(TranscriptionError):
        await stt.transcribe(b"")
    assert client.audio.transcriptions.calls == []


async def test_api_exception_is_wrapped():
    stt = WhisperTranscriber(api_key="k", client=fake_client(exc=RuntimeError("timeout")))
    with pytest.raises(TranscriptionError):
        await stt.transcribe(b"data")


def test_default_client_is_async_openai():
    from openai import AsyncOpenAI

    stt = WhisperTranscriber(api_key="k", base_url="http://localhost:9000/v1")
    assert isinstance(stt.client, AsyncOpenAI)
    assert str(stt.client.base_url).startswith("http://localhost:9000/v1")
