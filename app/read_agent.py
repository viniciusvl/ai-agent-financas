"""Agente de leitura: o LLM escolhe a consulta (tool calling); a aplicação calcula e formata.

Spec: specs/tasks/T15-read-path.md
"""

import json
import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI

from app.messages import MSG_LEITURA_NAO_SUPORTADA, MSG_NENHUM_GASTO, MSG_NENHUMA_PARCELA
from app.prompts import READ_AGENT_SYSTEM_PROMPT
from app.queries import (
    GastosRepository,
    ReadError,
    format_totais,
    format_valor,
    parcelas_futuras,
    total_periodo,
    total_por_categoria,
    total_por_metodo,
    ultimos,
)

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


def _parse_n_arg(valor: Any) -> int:
    """Interpreta o argumento opcional `n`; ausente usa o padrão 5."""
    if valor is None:
        return 5
    if isinstance(valor, bool):
        raise _ChamadaInvalida(f"n inválido: {valor!r}")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, str):
        try:
            return int(valor.strip())
        except ValueError as exc:
            raise _ChamadaInvalida(f"n inválido: {valor!r}") from exc
    raise _ChamadaInvalida(f"n inválido: {valor!r}")


def _format_data(valor: date) -> str:
    """Formata uma data como `dd/mm/aaaa`."""
    return f"{valor:%d/%m/%Y}"


def _format_mes(chave: str) -> str:
    """Converte `AAAA-MM` em `MM/AAAA`."""
    ano, mes = chave.split("-")
    return f"{mes}/{ano}"


class ReadAgent:
    """Escolhe a consulta via tool calling do LLM e (a partir da subtarefa 4) responde."""

    def __init__(
        self,
        api_key: str,
        repo: GastosRepository,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        timezone: str = "America/Sao_Paulo",
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
        elif nome == "ultimos_gastos":
            _parse_n_arg(argumentos.get("n"))

        return nome, argumentos

    async def answer(self, pergunta: str, agora: datetime) -> str:
        """Passos 1–5: escolhe a consulta via LLM, executa sobre a planilha e formata."""
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

        registros = self._carregar_registros()
        logger.debug("ferramenta escolhida: %s (%s)", nome, argumentos)
        return self._responder(nome, argumentos, registros, hoje)

    def _carregar_registros(self) -> list[Any]:
        """Lê os registros do repositório; qualquer falha vira `ReadError`."""
        try:
            return self.repo.registros()
        except ReadError:
            raise
        except Exception as exc:
            raise ReadError(f"falha ao ler a planilha: {exc}") from exc

    def _responder(
        self, nome: str, argumentos: dict[str, Any], registros: list[Any], hoje: date
    ) -> str:
        """Passos 4–5: executa a consulta escolhida e formata a resposta (datas dd/mm/aaaa)."""
        if nome in _FERRAMENTAS_PERIODO:
            inicio = _parse_data_arg(argumentos["inicio"])
            fim = _parse_data_arg(argumentos["fim"])
            if inicio > fim:
                inicio, fim = fim, inicio
            de, ate = _format_data(inicio), _format_data(fim)
            if nome == "total_periodo":
                totais = total_periodo(registros, inicio, fim)
                return f"💰 Total de {de} a {ate}: {format_totais(totais)}"
            if nome == "total_por_categoria":
                grupos = total_por_categoria(registros, inicio, fim)
                cabecalho = f"📊 Gastos por categoria de {de} a {ate}:"
            else:
                grupos = total_por_metodo(registros, inicio, fim)
                cabecalho = f"💳 Gastos por forma de pagamento de {de} a {ate}:"
            return self._format_grupos(cabecalho, grupos)

        if nome == "ultimos_gastos":
            n = max(1, min(20, _parse_n_arg(argumentos.get("n"))))
            lista = ultimos(registros, n)
            if not lista:
                return f"🧾 Últimos gastos:\n{MSG_NENHUM_GASTO}"
            linhas = [
                f"• {reg.data:%d/%m} — {reg.descricao} — "
                f"{format_valor(reg.moeda, reg.valor_compra)}"
                for reg in lista
            ]
            return "\n".join(["🧾 Últimos gastos:", *linhas])

        meses = parcelas_futuras(registros, hoje)
        if not meses:
            return f"📅 Parcelas futuras:\n{MSG_NENHUMA_PARCELA}"
        linhas = [
            f"• {_format_mes(chave)}: {format_totais(totais)}" for chave, totais in meses.items()
        ]
        return "\n".join(["📅 Parcelas futuras:", *linhas])

    @staticmethod
    def _format_grupos(cabecalho: str, grupos: dict[str, dict[str, Any]]) -> str:
        """Cabeçalho + uma linha `• {chave}: {totais}` por grupo (ordem alfabética)."""
        if not grupos:
            return f"{cabecalho}\n{MSG_NENHUM_GASTO}"
        linhas = [f"• {chave}: {format_totais(totais)}" for chave, totais in sorted(grupos.items())]
        return "\n".join([cabecalho, *linhas])
