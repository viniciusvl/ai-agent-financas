---
id: T08
title: App FastAPI do webhook e montagem das dependências
branch: feature/T08-webhook-app
depends_on: T16
acceptance: tests/acceptance/test_t08_webhook.py
allowed_paths:
  - app/main.py
---
## Contexto

`app/main.py` expõe o endpoint do webhook do Telegram e monta o `BotService` real.
Execução: `uvicorn --factory app.main:create_app`.

## Requisitos

- `create_app(settings=None, service=None) -> FastAPI`:
  - `settings` padrão = `get_settings()`; `telegram_webhook_secret` vazio → `ValueError`;
  - configurar `logging.basicConfig(level=settings.log_level)`;
  - se `service` for `None`, construir com `build_service(settings)` no **lifespan**
    (startup) e fechar o `TelegramClient` no shutdown;
  - `GET /health` → `{"status": "ok"}`;
  - `POST /telegram/webhook`:
    - header `X-Telegram-Bot-Api-Secret-Token` ausente/diferente → 403
      (comparar com `secrets.compare_digest`);
    - corpo não-JSON ou não-objeto → 400;
    - `update_id` já visto (guardar os últimos 1000 em memória) → 200 sem processar;
    - senão agenda `service.handle_update(update)` em `BackgroundTasks` e responde
      `{"ok": true}` imediatamente.
- `build_service(settings) -> BotService` (arquitetura v2, #23) monta, a partir de `settings`:
  - `schema = SheetSchema.load(settings.sheet_schema_path)`;
  - `TelegramClient`, `WhisperTranscriber` (key/model/language/base_url do Whisper);
  - `IntentRouter(api_key=typesafe_api_key, model=jev_model, base_url=jev_base_url,
    threshold=router_confidence_threshold, fallback=DeepSeekIntentFallback(...))`;
  - `PaymentExtractor(api_key=deepseek_api_key, schema=schema, model, base_url,
    default_currency, timezone)`;
  - `writer = PagamentoSheetWriter.from_service_account(google_service_account_file,
    google_sheet_id, schema)`;
  - `ReadAgent(api_key=deepseek_api_key, repo=GastosRepository(writer.worksheet, schema), ...)`;
  - `PendingStore(db_path, pending_ttl_seconds, model=Pagamento)` + `init()`;
  - `BotService(telegram, transcriber, router, extractor, read_agent, store, writer,
    allowed_user_ids=set(settings.allowed_user_ids), timezone=settings.timezone)`.
  - No shutdown (lifespan), fechar `TelegramClient` e `IntentRouter` (`aclose`).

## Subtarefas (uma por sessão)

1. `create_app` com `/health`, validação do segredo e despacho em background.
2. JSON inválido, deduplicação de `update_id`.
3. `build_service` e lifespan.

## Critérios de aceite

- `ACCEPTANCE_TASKS=T08 python -m pytest tests/acceptance/test_t08_webhook.py` passa 100%.
- `python -m pytest` passa e `ruff` limpo. Somente `app/main.py` (+ `tests/unit/`).

## Fora de escopo

Métricas, rate limiting.
