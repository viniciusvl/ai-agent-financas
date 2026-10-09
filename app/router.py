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

    async def _post_jev(self, texto: str) -> httpx.Response:
        """Faz a requisição ao Jev (passo 3 da spec)."""
        return await self.http.post(
            f"{self.base_url}/v1/systemone",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=self._jev_body(texto),
        )

    @staticmethod
    def _retry_after(response: httpx.Response) -> float:
        """Segundos a esperar após 429/529: `retry-after`, limitado a 5 (default 1)."""
        raw = response.headers.get("retry-after")
        try:
            seconds = float(raw)
        except (TypeError, ValueError):
            return 1.0
        return min(seconds, 5.0)

    async def _try_jev(self, texto: str) -> Rota | None:
        """Chama o Jev; devolve `None` em qualquer falha para acionar o fallback."""
        try:
            response = await self._post_jev(texto)
            if response.status_code in (429, 529):
                # Uma única nova tentativa após esperar o `retry-after`.
                await self.sleep(self._retry_after(response))
                response = await self._post_jev(texto)
        except httpx.HTTPError:
            return None

        if response.status_code != 200:
            return None
        try:
            return self._interpret_jev(response.json())
        except (ValueError, KeyError, TypeError):
            return None

    async def _fallback(self, texto: str) -> Rota:
        """Classifica pelo fallback; sem fallback ou com erro → `RouterError`."""
        if self.fallback is None:
            raise RouterError("Jev falhou e não há fallback configurado")
        try:
            return await self.fallback.classify(texto)
        except Exception as exc:  # noqa: BLE001 - qualquer erro vira RouterError
            raise RouterError("Jev falhou e o fallback também falhou") from exc

    def _finalize(self, rota: Rota) -> Rota:
        """Aplica o limiar (passo 7) e registra a decisão (passo 8)."""
        if rota.confianca < self.threshold:
            rota.intencao = Intencao.OUTRO
        logger.info(
            "Roteado: intencao=%s confianca=%.3f origem=%s modelo=%s",
            rota.intencao,
            rota.confianca,
            rota.origem,
            rota.modelo,
        )
        return rota

    async def route(self, texto: str) -> Rota:
        if not texto or not texto.strip():
            return Rota(Intencao.OUTRO, 0.0, origem="vazio")

        if self.api_key:
            rota = await self._try_jev(texto)
            if rota is not None:
                return self._finalize(rota)

        return self._finalize(await self._fallback(texto))

    async def aclose(self) -> None:
        if self._owns_http:
            await self.http.aclose()
