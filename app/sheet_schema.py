"""Formato padrão da planilha como configuração versionada (YAML).

O mesmo schema alimenta o contexto dos prompts e o escritor da planilha.
Spec: specs/tasks/T11-sheet-schema.md
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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
        """Lê o schema de um arquivo YAML (UTF-8) e valida via `from_dict`."""
        caminho = Path(path)
        try:
            texto = caminho.read_text(encoding="utf-8")
        except OSError as exc:
            raise SchemaError(f"não foi possível ler o schema {caminho}: {exc}") from exc
        try:
            data = yaml.safe_load(texto)
        except yaml.YAMLError as exc:
            raise SchemaError(f"YAML inválido em {caminho}: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SheetSchema":
        """Valida o mapeamento e devolve o schema; mensagens citam a coluna problemática."""
        if not isinstance(data, dict):
            raise SchemaError("schema deve ser um mapeamento com 'aba' e 'colunas'")

        aba = data.get("aba")
        if not isinstance(aba, str) or not aba.strip():
            raise SchemaError("schema sem 'aba' definida")

        colunas_raw = data.get("colunas")
        if not isinstance(colunas_raw, list) or not colunas_raw:
            raise SchemaError("schema sem 'colunas' definidas")

        campos_validos = set(CAMPOS_PAGAMENTO) | set(CAMPOS_EXTRAS)
        colunas: list[Coluna] = []
        nomes: set[str] = set()
        for raw in colunas_raw:
            if not isinstance(raw, dict):
                raise SchemaError("cada coluna deve ser um mapeamento com nome, campo e tipo")

            nome = raw.get("nome")
            if not isinstance(nome, str) or not nome.strip():
                raise SchemaError("coluna sem 'nome'")
            if nome in nomes:
                raise SchemaError(f"coluna {nome!r} está duplicada")

            campo = raw.get("campo")
            if not isinstance(campo, str) or not campo.strip():
                raise SchemaError(f"coluna {nome!r} sem 'campo'")
            if campo not in campos_validos:
                raise SchemaError(f"coluna {nome!r} tem 'campo' inválido: {campo!r}")

            tipo = raw.get("tipo")
            if not isinstance(tipo, str) or not tipo.strip():
                raise SchemaError(f"coluna {nome!r} sem 'tipo'")
            if tipo not in TIPOS:
                raise SchemaError(f"coluna {nome!r} tem 'tipo' inválido: {tipo!r}")

            formato = raw.get("formato")
            if formato is not None and not isinstance(formato, str):
                raise SchemaError(f"coluna {nome!r} tem 'formato' inválido: {formato!r}")

            obrigatoria = raw.get("obrigatoria", True)
            if not isinstance(obrigatoria, bool):
                obrigatoria = bool(obrigatoria)

            colunas.append(
                Coluna(
                    nome=nome,
                    campo=campo,
                    tipo=tipo,
                    formato=formato,
                    obrigatoria=obrigatoria,
                )
            )
            nomes.add(nome)

        return cls(aba=aba, colunas=tuple(colunas))

    def header(self) -> list[str]:
        raise NotImplementedError("T11")

    def to_row(self, pagamento: Pagamento, extras: dict[str, Any]) -> list[Any]:
        raise NotImplementedError("T11")

    def prompt_context(self) -> str:
        raise NotImplementedError("T11")

    def validate_header(self, header: list[str]) -> None:
        raise NotImplementedError("T11")
