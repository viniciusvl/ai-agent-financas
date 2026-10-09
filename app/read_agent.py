"""Agente de leitura: o LLM escolhe a consulta (tool calling); a aplicação calcula e formata.

Spec: specs/tasks/T15-read-path.md
"""

from datetime import datetime
from typing import Any

from app.queries import GastosRepository, ReadError

__all__ = ["TOOLS", "ReadAgent", "ReadError"]

TOOLS: list[dict[str, Any]] = []  # TODO(T15): definições das 5 ferramentas (formato OpenAI)


class ReadAgent:
    def __init__(
        self,
        api_key: str,
        repo: GastosRepository,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        timezone: str = "Asia/Shanghai",
        client: Any | None = None,
    ) -> None:
        raise NotImplementedError("T15")

    async def answer(self, pergunta: str, agora: datetime) -> str:
        raise NotImplementedError("T15")
