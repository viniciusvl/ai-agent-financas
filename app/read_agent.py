"""Agente de leitura: o LLM escolhe a consulta (tool calling); a aplicação calcula e formata.

Spec: specs/tasks/T15-read-path.md
"""

import json
import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI

from app.messages import MSG_LEITURA_NAO_SUPORTADA
from app.prompts import READ_AGENT_SYSTEM_PROMPT
from app.queries import GastosRepository, ReadError

logger = logging.getLogger(__name__)

__all__ = ["TOOLS", "ReadAgent", "ReadError"]

# Nomes dos dias da semana (0 = segunda) para o placeholder `{dia_semana}` do prompt.
_DIAS_SEMANA = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)

# Ferramentas que o agente sabe executar (qualquer outro nome é recusado).
_FERRAMENTAS = frozenset(
    {
        "total_periodo",
        "total_por_categoria",
        "total_por_metodo",
        "ultimos_gastos",
        "parcelas_futuras",
    }
)

# Ferramentas que exigem `inicio` e `fim` (datas no formato YYYY-MM-DD).
_FERRAMENTAS_PERIODO = frozenset({"total_periodo", "total_por_categoria", "total_por_metodo"})


def _ferramenta_periodo(nome: str, descricao: str) -> dict[str, Any]:
    """Monta a definição (formato OpenAI) de uma ferramenta com período `inicio`/`fim`."""
    return {
        "type": "function",
        "function": {
            "name": nome,
            "description": descricao,
            "parameters": {
                "type": "object",
                "properties": {
                    "inicio": {
                        "type": "string",
                        "description": "Data inicial do período, inclusive, no formato YYYY-MM-DD.",
                    },
                    "fim": {
                        "type": "string",
                        "description": "Data final do período, inclusive, no formato YYYY-MM-DD.",
                    },
                },
                "required": ["inicio", "fim"],
                "additionalProperties": False,
            },
        },
    }


TOOLS: list[dict[str, Any]] = [
    _ferramenta_periodo("total_periodo", "Soma total gasta em um período, por moeda."),
    _ferramenta_periodo("total_por_categoria", "Soma gasta por categoria em um período."),
    _ferramenta_periodo("total_por_metodo", "Soma gasta por forma de pagamento em um período."),
    {
        "type": "function",
        "function": {
            "name": "ultimos_gastos",
            "description": "Lista os últimos gastos registrados (quantidade padrão: 5).",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {
                        "type": "integer",
                        "description": "Quantidade de gastos a listar (1 a 20; padrão 5).",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parcelas_futuras",
            "description": "Lista as parcelas futuras de compras no crédito parcelado, por mês.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]


class _ChamadaInvalida(Exception):
    """Chamada de ferramenta ausente, desconhecida ou com argumentos inválidos."""


def _parse_data_arg(valor: Any) -> date:
    """Interpreta um argumento de data no formato `YYYY-MM-DD`."""
    if not isinstance(valor, str):
        raise _ChamadaInvalida(f"data inválida: {valor!r}")
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError as exc:
        raise _ChamadaInvalida(f"data inválida: {valor!r}") from exc


class ReadAgent:
    """Escolhe a consulta via tool calling do LLM e (a partir da subtarefa 4) responde."""

    def __init__(
        self,
        api_key: str,
        repo: GastosRepository,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        timezone: str = "Asia/Shanghai",
        client: Any | None = None,
    ) -> None:
        self.repo = repo
        self.model = model
        self.timezone = timezone
        self.client = (
            client if client is not None else AsyncOpenAI(api_key=api_key, base_url=base_url)
        )

    def _extrair_chamada(self, resposta: Any) -> tuple[str, dict[str, Any]]:
        """Extrai `(nome, argumentos)` da 1ª tool call; inválida → `_ChamadaInvalida`."""
        try:
            escolhas = resposta.choices
            mensagem = escolhas[0].message if escolhas else None
        except (AttributeError, IndexError, TypeError) as exc:
            raise _ChamadaInvalida("resposta do LLM malformada") from exc

        chamadas = getattr(mensagem, "tool_calls", None)
        if not chamadas:
            raise _ChamadaInvalida("nenhuma ferramenta escolhida")

        funcao = getattr(chamadas[0], "function", None)
        nome = getattr(funcao, "name", None)
        if nome not in _FERRAMENTAS:
            raise _ChamadaInvalida(f"ferramenta desconhecida: {nome!r}")

        bruto = getattr(funcao, "arguments", None)
        try:
            argumentos = json.loads(bruto) if bruto else {}
        except (TypeError, ValueError) as exc:
            raise _ChamadaInvalida("argumentos não são JSON válido") from exc
        if not isinstance(argumentos, dict):
            raise _ChamadaInvalida("argumentos não são um objeto JSON")

        if nome in _FERRAMENTAS_PERIODO:
            for campo in ("inicio", "fim"):
                if campo not in argumentos:
                    raise _ChamadaInvalida(f"argumento obrigatório ausente: {campo}")
                _parse_data_arg(argumentos[campo])

        return nome, argumentos

    async def answer(self, pergunta: str, agora: datetime) -> str:
        """Passos 1–3: monta as mensagens, chama o LLM e valida a tool call escolhida."""
        hoje = agora.astimezone(ZoneInfo(self.timezone)).date()
        dia_semana = _DIAS_SEMANA[hoje.weekday()]
        mensagens = [
            {
                "role": "system",
                "content": READ_AGENT_SYSTEM_PROMPT.format(
                    hoje=hoje.isoformat(), dia_semana=dia_semana
                ),
            },
            {"role": "user", "content": pergunta},
        ]

        try:
            resposta = await self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                tools=TOOLS,
                tool_choice="auto",
                messages=mensagens,
            )
        except Exception as exc:  # qualquer falha do LLM vira ReadError
            raise ReadError(f"falha ao consultar o LLM: {exc}") from exc

        try:
            nome, argumentos = self._extrair_chamada(resposta)
        except _ChamadaInvalida as exc:
            logger.warning("consulta de leitura não suportada: %s", exc)
            return MSG_LEITURA_NAO_SUPORTADA

        # TODO(subtarefa 4): executar a consulta sobre `self.repo.registros()` e formatar
        # a resposta (passos 4–5). Até lá, uma chamada válida ainda não é respondida.
        logger.debug("ferramenta escolhida: %s (%s)", nome, argumentos)
        return MSG_LEITURA_NAO_SUPORTADA
