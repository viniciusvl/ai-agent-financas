"""Configuração da aplicação, lida de variáveis de ambiente / arquivo .env."""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    public_base_url: str = ""
    allowed_user_ids: Annotated[list[int], NoDecode] = []

    # Whisper (STT) — endpoint compatível com a API da OpenAI
    whisper_api_key: str = ""
    whisper_base_url: str | None = None
    whisper_model: str = "whisper-1"
    whisper_language: str = "pt"

    # DeepSeek (extração)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"

    # Jev (TypeSafe) — roteador de intenção
    typesafe_api_key: str = ""
    jev_model: str = "jev-1.13.0"
    jev_base_url: str = "https://api.typesafe.ai"
    router_confidence_threshold: float = 0.6

    # Schema da planilha (formato padrão)
    sheet_schema_path: str = "config/planilha.yaml"

    # Google Sheets
    google_service_account_file: str = "secrets/google-service-account.json"
    google_sheet_id: str = ""
    google_worksheet_name: str = "Gastos"

    # App
    timezone: str = "America/Sao_Paulo"
    default_currency: str = "BRL"
    db_path: str = "data/bot.db"
    pending_ttl_seconds: int = 86400
    log_level: str = "INFO"

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.split(",") if part.strip()]
        return value

    @field_validator("whisper_base_url", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        return value or None

    @field_validator("public_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
