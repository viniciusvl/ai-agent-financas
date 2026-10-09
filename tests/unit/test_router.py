"""Testes unitários do roteador de intenção (subpassos 1, 3 e 5 da T12)."""

import pytest

from app.router import Intencao, IntentRouter, Rota


class FakeResponse:
    def __init__(self, data):
        self._data = data

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
