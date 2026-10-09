"""Testes unitários do roteador de intenção (subpassos 1, 3 e 5 da T12)."""

import pytest

from app.router import Intencao, IntentRouter, Rota, RouterError


class FakeResponse:
    def __init__(self, data, status_code=200, headers=None):
        self._data = data
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._data


class FakeHttp:
    """Client httpx falso: registra chamadas e devolve uma resposta fixa."""

    def __init__(self, response=None):
        # Um dict é interpretado como o JSON de uma resposta do Jev.
        if isinstance(response, dict):
            response = FakeResponse(response)
        self.response = response
        self.requests = []
        self.closed = False

    async def post(self, url, headers=None, json=None):
        self.requests.append((url, headers, json))
        return self.response

    async def aclose(self):
        self.closed = True


def jev_json(choice, probabilities, model="jev-1.13.0"):
    return {
        "model": model,
        "answers": {"intencao": {"choice": choice, "probabilities": probabilities}},
    }


def test_rota_defaults():
    rota = Rota(Intencao.OUTRO, 0.0, origem="vazio")
    assert rota.probabilidades == {}
    assert rota.modelo is None


async def test_empty_text_makes_no_request():
    http = FakeHttp()
    router = IntentRouter(api_key="k", base_url="https://x.test", http=http)
    rota = await router.route("   ")
    assert rota.intencao is Intencao.OUTRO
    assert rota.confianca == 0.0
    assert rota.origem == "vazio"
    assert http.requests == []


async def test_request_shape_and_interpretation():
    http = FakeHttp(jev_json("escrita", {"escrita": 0.8, "leitura": 0.1, "outro": 0.1}))
    router = IntentRouter(api_key="k", base_url="https://x.test", http=http)
    rota = await router.route("paguei 10")
    url, headers, body = http.requests[0]
    assert url == "https://x.test/v1/systemone"
    assert headers["Authorization"] == "Bearer k"
    assert body["state"] == "paguei 10"
    assert body["model"] == "jev-1.13.0"
    assert rota.intencao is Intencao.ESCRITA
    assert rota.confianca == pytest.approx(0.8)
    assert rota.origem == "jev"
    assert rota.modelo == "jev-1.13.0"


async def test_probabilities_are_normalized():
    http = FakeHttp(jev_json("leitura", {"escrita": 0.25, "leitura": 0.72, "outro": 0.22}))
    router = IntentRouter(api_key="k", base_url="https://x.test", http=http)
    rota = await router.route("quanto gastei?")
    assert rota.intencao is Intencao.LEITURA
    assert sum(rota.probabilidades.values()) == pytest.approx(1.0)
    assert rota.confianca == pytest.approx(0.72 / 1.19)


async def test_injected_client_is_not_closed():
    http = FakeHttp()
    router = IntentRouter(api_key="k", base_url="https://x.test", http=http)
    await router.aclose()
    assert http.closed is False


async def test_own_client_is_closed():
    router = IntentRouter(api_key="k", base_url="https://x.test")
    await router.aclose()
    assert router.http.is_closed


# --- subtarefa 2: retry, fallback, RouterError e limiar ----------------------------------------


class FakeJevResponse:
    """Resposta httpx mínima: status, headers e corpo JSON."""

    def __init__(self, status_code=200, data=None, headers=None):
        self.status_code = status_code
        self._data = data
        self.headers = headers or {}

    def json(self):
        if self._data is None:
            raise ValueError("not json")
        return self._data


class SequencedHttp:
    """Devolve respostas em sequência e registra as chamadas."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    async def post(self, url, headers=None, json=None):
        self.requests.append((url, headers, json))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self):
        pass


class FakeFallback:
    """Fallback falso que devolve uma rota fixa ou levanta uma exceção."""

    def __init__(self, rota=None, exc=None):
        self.rota = rota or Rota(Intencao.LEITURA, 0.9, origem="fallback")
        self.exc = exc
        self.calls = []

    async def classify(self, texto):
        self.calls.append(texto)
        if self.exc:
            raise self.exc
        return self.rota


class RecordingSleep:
    def __init__(self):
        self.calls = []

    async def __call__(self, seconds):
        self.calls.append(seconds)


def make_router(http, **kw):
    params = dict(api_key="k", base_url="https://x.test", http=http, fallback=FakeFallback())
    params.update(kw)
    return IntentRouter(**params)


async def test_retry_on_429_uses_retry_after():
    sleeps = RecordingSleep()
    http = SequencedHttp(
        [
            FakeJevResponse(429, headers={"retry-after": "2"}),
            FakeJevResponse(200, jev_json("escrita", {"escrita": 1.0})),
        ]
    )
    rota = await make_router(http, sleep=sleeps).route("paguei 10")
    assert rota.intencao is Intencao.ESCRITA
    assert sleeps.calls == [2.0]
    assert len(http.requests) == 2


async def test_retry_after_is_capped_and_defaulted():
    sleeps = RecordingSleep()
    http = SequencedHttp(
        [
            FakeJevResponse(529, headers={"retry-after": "60"}),
            FakeJevResponse(529),
        ]
    )
    fallback = FakeFallback()
    rota = await make_router(http, sleep=sleeps, fallback=fallback).route("paguei 10")
    assert sleeps.calls == [5.0]
    assert rota.origem == "fallback"
    assert fallback.calls == ["paguei 10"]


async def test_malformed_response_uses_fallback():
    http = SequencedHttp([FakeJevResponse(200)])
    fallback = FakeFallback()
    rota = await make_router(http, fallback=fallback).route("quanto gastei?")
    assert rota.origem == "fallback"
    assert fallback.calls == ["quanto gastei?"]


async def test_non_2xx_uses_fallback():
    http = SequencedHttp([FakeJevResponse(500)])
    fallback = FakeFallback()
    rota = await make_router(http, fallback=fallback).route("quanto gastei?")
    assert rota.origem == "fallback"


async def test_network_error_uses_fallback():
    import httpx

    http = SequencedHttp([httpx.ReadTimeout("slow")])
    fallback = FakeFallback()
    rota = await make_router(http, fallback=fallback).route("quanto gastei?")
    assert rota.origem == "fallback"


async def test_empty_api_key_skips_jev():
    http = SequencedHttp([])
    fallback = FakeFallback()
    rota = await make_router(http, api_key="", fallback=fallback).route("oi")
    assert http.requests == []
    assert rota.origem == "fallback"


async def test_router_error_without_fallback():
    http = SequencedHttp([FakeJevResponse(500)])
    with pytest.raises(RouterError):
        await make_router(http, fallback=None).route("x")


async def test_router_error_when_fallback_fails():
    http = SequencedHttp([FakeJevResponse(500)])
    fallback = FakeFallback(exc=RuntimeError("down"))
    with pytest.raises(RouterError):
        await make_router(http, fallback=fallback).route("x")


async def test_low_confidence_jev_becomes_outro():
    http = FakeHttp(jev_json("escrita", {"escrita": 0.45, "leitura": 0.35, "outro": 0.2}))
    router = IntentRouter(api_key="k", base_url="https://x.test", http=http, threshold=0.6)
    rota = await router.route("taxi")
    assert rota.intencao is Intencao.OUTRO
    assert rota.confianca == pytest.approx(0.45)
    assert rota.origem == "jev"


async def test_low_confidence_fallback_becomes_outro():
    http = SequencedHttp([FakeJevResponse(500)])
    fallback = FakeFallback(Rota(Intencao.ESCRITA, 0.3, origem="fallback"))
    rota = await make_router(http, fallback=fallback).route("hmm")
    assert rota.intencao is Intencao.OUTRO
    assert rota.origem == "fallback"
