"""Formato padrão da planilha como configuração versionada (YAML).

O mesmo schema alimenta o contexto dos prompts e o escritor da planilha.
Spec: specs/tasks/T11-sheet-schema.md
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.payment import Pagamento

TIPOS = ("texto", "data", "hora", "datahora", "moeda", "inteiro", "enum")

# Campos que uma coluna pode referenciar.
CAMPOS_PAGAMENTO = (
    "metodo_pagamento",
    "data",
    "hora",
    "quant_parcelas",
    "valor_compra",
    "moeda",
    "categoria",
    "descricao",
    "texto_original",
    "valor_parcela",
    "valor_primeira_parcela",
)
CAMPOS_EXTRAS = ("id", "usuario", "registrado_em")


class SchemaError(Exception):
    """Schema inválido, cabeçalho divergente ou valor obrigatório ausente."""


@dataclass(frozen=True)
class Coluna:
    nome: str
    campo: str
    tipo: str
    formato: str | None = None
    obrigatoria: bool = True


@dataclass(frozen=True)
class SheetSchema:
    aba: str
    colunas: tuple[Coluna, ...]

    @classmethod
    def load(cls, path: str | Path) -> "SheetSchema":
        raise NotImplementedError("T11")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SheetSchema":
        raise NotImplementedError("T11")

    def header(self) -> list[str]:
        raise NotImplementedError("T11")

    def to_row(self, pagamento: Pagamento, extras: dict[str, Any]) -> list[Any]:
        raise NotImplementedError("T11")

    def prompt_context(self) -> str:
        raise NotImplementedError("T11")

    def validate_header(self, header: list[str]) -> None:
        raise NotImplementedError("T11")
