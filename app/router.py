"""Roteador de intenção (escrita / leitura / outro) usando o Jev (TypeSafe), com fallback no
DeepSeek. Spec: specs/tasks/T12-intent-router.md
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

from app.prompts import ROUTER_CRITERIA, ROUTER_INSTRUCTIONS

logger = logging.getLogger(__name__)

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
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.threshold = threshold
        self.timeout = timeout
        self.fallback = fallback
        self.sleep = sleep
        # Só fecha o client que criou; um client injetado pertence ao chamador.
        self._owns_http = http is None
        self.http: httpx.AsyncClient = (
            http if http is not None else httpx.AsyncClient(timeout=timeout)
        )

    def _jev_body(self, texto: str) -> dict[str, Any]:
        """Corpo exato esperado pelo Jev; o texto vai somente no campo `state`."""
        return {
            "model": self.model,
            "state": texto,
            "questions": {
                "intencao": {
                    "type": "choice",
                    "instructions": ROUTER_INSTRUCTIONS,
                    "criteria": ROUTER_CRITERIA,
                }
            },
        }

    @staticmethod
    def _normalize(probabilities: dict[str, Any]) -> dict[str, float]:
        """Converte as probabilidades para float e normaliza para somar 1 (se possível)."""
        probs = {chave: float(valor) for chave, valor in probabilities.items()}
        total = sum(probs.values())
        if total > 0:
            return {chave: valor / total for chave, valor in probs.items()}
        return probs

    def _interpret_jev(self, data: dict[str, Any]) -> Rota:
        """Interpreta uma resposta 200 do Jev (passo 5 da spec)."""
        answer = data["answers"]["intencao"]
        probs = self._normalize(answer["probabilities"])
        try:
            intencao = Intencao(answer.get("choice"))
        except ValueError:
            intencao = Intencao(max(probs, key=probs.__getitem__))
        return Rota(
            intencao=intencao,
            confianca=probs.get(intencao.value, 0.0),
            origem="jev",
            probabilidades=probs,
            modelo=data.get("model"),
        )

    async def route(self, texto: str) -> Rota:
        if not texto or not texto.strip():
            return Rota(Intencao.OUTRO, 0.0, origem="vazio")

        response = await self.http.post(
            f"{self.base_url}/v1/systemone",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=self._jev_body(texto),
        )
        rota = self._interpret_jev(response.json())
        logger.info(
            "Roteado: intencao=%s confianca=%.3f origem=%s modelo=%s",
            rota.intencao,
            rota.confianca,
            rota.origem,
            rota.modelo,
        )
        return rota

    async def aclose(self) -> None:
        if self._owns_http:
            await self.http.aclose()
