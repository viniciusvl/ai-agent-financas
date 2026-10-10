"""Testes unitários do `ReadAgent` (subtarefa 3): TOOLS e chamada ao LLM. Spec: T15."""

import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from openai import AsyncOpenAI

from app.messages import MSG_LEITURA_NAO_SUPORTADA
from app.prompts import READ_AGENT_SYSTEM_PROMPT
from app.queries import ReadError
from app.read_agent import TOOLS, ReadAgent

AGORA = datetime(2026, 10, 8, 23, 30, tzinfo=ZoneInfo("UTC"))  # 08/10 (quinta) em São Paulo


class FakeRepo:
    def registros(self):
        return []


class FakeCompletions:
    def __init__(self, tool=None, args=None, raw_args=None, exc=None, no_tool=False):
        self.tool, self.args, self.raw_args = tool, args, raw_args
        self.exc, self.no_tool, self.calls = exc, no_tool, []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        if self.no_tool:
            message = SimpleNamespace(content="não sei", tool_calls=None)
        else:
            arguments = self.raw_args if self.raw_args is not None else json.dumps(self.args or {})
            call = SimpleNamespace(
                id="c1",
                type="function",
                function=SimpleNamespace(name=self.tool, arguments=arguments),
            )
            message = SimpleNamespace(content=None, tool_calls=[call])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _agent(**kw):
    completions = FakeCompletions(**kw)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return ReadAgent(api_key="k", repo=FakeRepo(), client=client), completions


def test_tools_tem_as_cinco_ferramentas():
    nomes = {t["function"]["name"] for t in TOOLS}
    assert nomes == {
        "total_periodo",
        "total_por_categoria",
        "total_por_metodo",
        "ultimos_gastos",
        "parcelas_futuras",
    }
    assert all(t["type"] == "function" for t in TOOLS)
    for nome in ("total_periodo", "total_por_categoria", "total_por_metodo"):
        params = next(t for t in TOOLS if t["function"]["name"] == nome)["function"]["parameters"]
        assert set(params["required"]) == {"inicio", "fim"}


def test_client_padrao_e_async_openai():
    assert isinstance(ReadAgent(api_key="k", repo=FakeRepo()).client, AsyncOpenAI)


async def test_answer_envia_parametros_esperados():
    ag, completions = _agent(
        tool="total_periodo", args={"inicio": "2026-10-05", "fim": "2026-10-06"}
    )
    await ag.answer("quanto gastei?", AGORA)
    call = completions.calls[0]
    assert call["model"] == "deepseek-flash"
    assert call["temperature"] == 0
    assert call["tools"] == TOOLS
    assert call["tool_choice"] == "auto"
    assert call["messages"] == [
        {
            "role": "system",
            "content": READ_AGENT_SYSTEM_PROMPT.format(
                hoje="2026-10-08", dia_semana="quinta-feira"
            ),
        },
        {"role": "user", "content": "quanto gastei?"},
    ]


@pytest.mark.parametrize(
    "kw",
    [
        {"no_tool": True},
        {"tool": "apagar_tudo", "args": {}},
        {"tool": "total_periodo", "raw_args": "{não é json"},
        {"tool": "total_periodo", "args": {"inicio": "ontem", "fim": "2026-10-09"}},
        {"tool": "total_periodo", "args": {"inicio": "2026-10-01"}},
        {"tool": "parcelas_futuras", "args": "não é objeto"},
    ],
)
async def test_answer_nao_suportada(kw):
    ag, _ = _agent(**kw)
    assert await ag.answer("qual a capital da França?", AGORA) == MSG_LEITURA_NAO_SUPORTADA


async def test_answer_erro_do_llm_vira_read_error():
    ag, _ = _agent(exc=RuntimeError("timeout"))
    with pytest.raises(ReadError):
        await ag.answer("?", AGORA)
