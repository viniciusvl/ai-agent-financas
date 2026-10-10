import json
import logging
from types import SimpleNamespace

import httpx
import pytest
import respx

from app.prompts import ROUTER_CRITERIA, ROUTER_FALLBACK_SYSTEM_PROMPT, ROUTER_INSTRUCTIONS
from app.router import DeepSeekIntentFallback, Intencao, IntentRouter, Rota, RouterError

pytestmark = pytest.mark.task("T12")

BASE = "https://jev.test"
URL = f"{BASE}/v1/systemone"
KEY = "ts-secret-key-123"


def jev_answer(choice, probabilities, model="jev-1.13.0"):
    return httpx.Response(
        200,
        json={
            "model": model,
            "answers": {
                "intencao": {
                    "type": "choice",
                    "choice": choice,
                    "probabilities": probabilities,
                    "confidence": 0.5,
                }
            },
            "usage": {"input_tokens": 50, "output_tokens": 3},
        },
    )


class FakeFallback:
    def __init__(self, rota=None, exc=None):
        self.rota = rota or Rota(Intencao.LEITURA, 0.9, origem="fallback")
        self.exc = exc
        self.calls = []

    async def classify(self, texto):
        self.calls.append(texto)
        if self.exc:
            raise self.exc
        return self.rota


class Sleeps:
    def __init__(self):
        self.calls = []

    async def __call__(self, seconds):
        self.calls.append(seconds)


@pytest.fixture
async def http():
    async with httpx.AsyncClient() as client:
        yield client


def make_router(http, **kw):
    params = dict(api_key=KEY, base_url=BASE, http=http, fallback=FakeFallback(), sleep=Sleeps())
    params.update(kw)
    return IntentRouter(**params)


@respx.mock
async def test_request_shape_and_choice(http):
    route = respx.post(URL).mock(
        return_value=jev_answer("escrita", {"escrita": 0.9, "leitura": 0.05, "outro": 0.05})
    )
    rota = await make_router(http).route("paguei 80 reais no mercado")
    request = route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {
        "model": "jev-1.13.0",
        "state": "paguei 80 reais no mercado",
        "questions": {
            "intencao": {
                "type": "choice",
                "instructions": ROUTER_INSTRUCTIONS,
                "criteria": ROUTER_CRITERIA,
            }
        },
    }
    assert rota.intencao is Intencao.ESCRITA
    assert rota.origem == "jev"
    assert rota.modelo == "jev-1.13.0"
    assert rota.confianca == pytest.approx(0.9)


@respx.mock
async def test_probabilities_are_normalized(http):
    respx.post(URL).mock(
        return_value=jev_answer("leitura", {"escrita": 0.25, "leitura": 0.72, "outro": 0.22})
    )
    rota = await make_router(http).route("quanto gastei ontem?")
    assert rota.intencao is Intencao.LEITURA
    assert sum(rota.probabilidades.values()) == pytest.approx(1.0)
    assert rota.confianca == pytest.approx(0.72 / 1.19)


@respx.mock
async def test_invalid_choice_uses_argmax(http):
    respx.post(URL).mock(
        return_value=jev_answer("???", {"escrita": 0.1, "leitura": 0.8, "outro": 0.1})
    )
    rota = await make_router(http).route("quais parcelas faltam?")
    assert rota.intencao is Intencao.LEITURA


@respx.mock
async def test_low_confidence_becomes_outro(http):
    respx.post(URL).mock(
        return_value=jev_answer("escrita", {"escrita": 0.45, "leitura": 0.35, "outro": 0.2})
    )
    rota = await make_router(http, threshold=0.6).route("taxi")
    assert rota.intencao is Intencao.OUTRO
    assert rota.confianca == pytest.approx(0.45)
    assert rota.origem == "jev"


@pytest.mark.parametrize("texto", ["", "   ", "\n"])
@respx.mock
async def test_empty_text_makes_no_request(http, texto):
    route = respx.post(URL)
    rota = await make_router(http).route(texto)
    assert rota.intencao is Intencao.OUTRO
    assert rota.origem == "vazio"
    assert not route.called


@respx.mock
async def test_retry_on_429_respects_retry_after(http):
    sleeps = Sleeps()
    respx.post(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "2"}),
            jev_answer("escrita", {"escrita": 1.0, "leitura": 0.0, "outro": 0.0}),
        ]
    )
    rota = await make_router(http, sleep=sleeps).route("paguei 10")
    assert rota.intencao is Intencao.ESCRITA
    assert sleeps.calls == [2.0]


@respx.mock
async def test_retry_after_is_capped_and_defaulted(http):
    sleeps = Sleeps()
    respx.post(URL).mock(
        side_effect=[
            httpx.Response(529, headers={"retry-after": "60"}),
            httpx.Response(529),
        ]
    )
    fallback = FakeFallback()
    rota = await make_router(http, sleep=sleeps, fallback=fallback).route("paguei 10")
    assert sleeps.calls == [5.0]
    assert rota.origem == "fallback"
    assert fallback.calls == ["paguei 10"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"error": "unauthorized"}),
        httpx.Response(422, json={"error": "bad"}),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json={"model": "jev-1.13.0", "answers": {}}),
        httpx.Response(200, json={"answers": {"intencao": {"choice": "x", "probabilities": {}}}}),
    ],
)
@respx.mock
async def test_failures_use_fallback(http, response):
    respx.post(URL).mock(return_value=response)
    fallback = FakeFallback()
    rota = await make_router(http, fallback=fallback).route("quanto gastei?")
    assert rota.origem == "fallback"
    assert rota.intencao is Intencao.LEITURA
    assert fallback.calls == ["quanto gastei?"]


@respx.mock
async def test_timeout_uses_fallback(http):
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    rota = await make_router(http).route("quanto gastei?")
    assert rota.origem == "fallback"


@respx.mock
async def test_without_api_key_goes_straight_to_fallback(http):
    route = respx.post(URL)
    fallback = FakeFallback()
    rota = await make_router(http, api_key="", fallback=fallback).route("oi")
    assert not route.called
    assert rota.origem == "fallback"


@respx.mock
async def test_fallback_low_confidence_also_becomes_outro(http):
    respx.post(URL).mock(return_value=httpx.Response(500))
    fallback = FakeFallback(Rota(Intencao.ESCRITA, 0.3, origem="fallback"))
    rota = await make_router(http, fallback=fallback).route("hmm")
    assert rota.intencao is Intencao.OUTRO
    assert rota.origem == "fallback"


@respx.mock
async def test_router_error_when_everything_fails(http):
    respx.post(URL).mock(return_value=httpx.Response(500))
    with pytest.raises(RouterError) as exc:
        await make_router(http, fallback=FakeFallback(exc=RuntimeError("down"))).route("x")
    assert KEY not in str(exc.value)
    with pytest.raises(RouterError):
        await make_router(http, fallback=None).route("x")


@respx.mock
async def test_key_never_logged(http, caplog):
    caplog.set_level(logging.DEBUG)
    respx.post(URL).mock(return_value=httpx.Response(401))
    await make_router(http).route("quanto gastei?")
    respx.post(URL).mock(
        return_value=jev_answer("escrita", {"escrita": 1.0, "leitura": 0.0, "outro": 0.0})
    )
    await make_router(http).route("paguei 5")
    assert KEY not in caplog.text


@respx.mock
async def test_own_client_is_closed():
    respx.post(URL).mock(
        return_value=jev_answer("outro", {"escrita": 0.0, "leitura": 0.0, "outro": 1.0})
    )
    router = IntentRouter(api_key=KEY, base_url=BASE, fallback=FakeFallback())
    try:
        assert (await router.route("oi")).intencao is Intencao.OUTRO
    finally:
        await router.aclose()


# --- DeepSeekIntentFallback --------------------------------------------------------------------


class FakeCompletions:
    def __init__(self, content=None, exc=None, empty=False):
        self.content, self.exc, self.empty, self.calls = content, exc, empty, []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        if self.empty:
            return SimpleNamespace(choices=[])
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_fallback(**kw):
    completions = FakeCompletions(**kw)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return DeepSeekIntentFallback(api_key="k", client=client), completions


async def test_fallback_request_and_parse():
    fb, completions = make_fallback(content='{"intencao": "leitura", "confianca": 0.83}')
    rota = await fb.classify("quanto gastei?")
    call = completions.calls[0]
    assert call["model"] == "deepseek-flash"
    assert call["temperature"] == 0
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"][0] == {
        "role": "system",
        "content": ROUTER_FALLBACK_SYSTEM_PROMPT.format(**ROUTER_CRITERIA),
    }
    assert call["messages"][-1] == {"role": "user", "content": "quanto gastei?"}
    assert rota.intencao is Intencao.LEITURA
    assert rota.confianca == pytest.approx(0.83)
    assert rota.origem == "fallback"


@pytest.mark.parametrize(
    "kw",
    [
        {"content": "nada"},
        {"content": '{"intencao": "comprar", "confianca": 0.9}'},
        {"content": '{"intencao": "escrita"}'},
        {"content": '{"intencao": "escrita", "confianca": "alta"}'},
        {"empty": True},
    ],
)
async def test_fallback_malformed_is_outro(kw):
    fb, _ = make_fallback(**kw)
    rota = await fb.classify("x")
    assert rota.intencao is Intencao.OUTRO
    assert rota.confianca == 0.0
    assert rota.origem == "fallback"


async def test_fallback_confidence_is_clamped():
    fb, _ = make_fallback(content='{"intencao": "escrita", "confianca": 1.7}')
    assert (await fb.classify("x")).confianca == 1.0


async def test_fallback_api_error_raises_router_error():
    fb, _ = make_fallback(exc=RuntimeError("401"))
    with pytest.raises(RouterError):
        await fb.classify("x")


def test_fallback_default_client():
    from openai import AsyncOpenAI

    fb = DeepSeekIntentFallback(api_key="k")
    assert isinstance(fb.client, AsyncOpenAI)
