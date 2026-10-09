"""Roteador de intenção (escrita / leitura / outro) usando o Jev (TypeSafe), com fallback no
DeepSeek. Spec: specs/tasks/T12-intent-router.md
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

JEV_DEFAULT_MODEL = "jev-1.13.0"
JEV_DEFAULT_BASE_URL = "https://api.typesafe.ai"


class Intencao(StrEnum):
    ESCRITA = "escrita"
    LEITURA = "leitura"
    OUTRO = "outro"


class RouterError(Exception):
    """O Jev e o fallback falharam."""


@dataclass
class Rota:
    intencao: Intencao
    confianca: float
    origem: str  # "jev" | "fallback" | "vazio"
    probabilidades: dict[str, float] = field(default_factory=dict)
    modelo: str | None = None


class DeepSeekIntentFallback:
    """Classificador JSON no DeepSeek usado quando o Jev falha."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        client: Any | None = None,
    ) -> None:
        raise NotImplementedError("T12")

    async def classify(self, texto: str) -> Rota:
        raise NotImplementedError("T12")


class IntentRouter:
    def __init__(
        self,
        api_key: str,
        model: str = JEV_DEFAULT_MODEL,
        base_url: str = JEV_DEFAULT_BASE_URL,
        threshold: float = 0.6,
        timeout: float = 3.0,
        http: httpx.AsyncClient | None = None,
        fallback: Any | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        raise NotImplementedError("T12")

    async def route(self, texto: str) -> Rota:
        raise NotImplementedError("T12")

    async def aclose(self) -> None:
        raise NotImplementedError("T12")
