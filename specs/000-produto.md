# Spec de produto — ai-agent-financas

## Objetivo

Registrar e consultar, com o mínimo de atrito, gastos pessoais numa **planilha específica do
Google Sheets**, a partir de mensagens de texto ou áudio enviadas a um bot do Telegram. O
modelo da planilha é definido pelo dono e descrito em `config/planilha.yaml`.

## Fluxo principal

1. Usuário autorizado envia ao bot um **texto** ("gastei 35 reais no almoço, pix") ou um
   **áudio** (voice note ou arquivo de áudio).
2. O Telegram entrega o update via **webhook HTTPS** ao servidor (EC2, domínio próprio).
3. Se for áudio, o servidor transcreve com **Whisper**; o bot responde com a transcrição.
4. O **roteador** decide entre registrar (escrita), consultar (leitura) ou outro.
5. Escrita: o **DeepSeek** extrai o pagamento; a aplicação calcula as parcelas; o bot pede
   confirmação (**✅ Confirmar** / **❌ Cancelar**) e grava a linha no formato da planilha.
6. Leitura: o DeepSeek escolhe a consulta; a aplicação calcula e responde.

## Dados de um pagamento

| Campo | Tipo | Regra |
|---|---|---|
| valor_compra | Decimal | > 0, 2 casas decimais |
| moeda | BRL / USD / EUR | padrão BRL |
| metodo_pagamento | dinheiro, débito, crédito à vista, crédito parcelado, Pix, boleto, transferência, outro | padrão outro |
| quant_parcelas | inteiro | 2–24 só no crédito parcelado |
| categoria | alimentação, transporte, hospedagem, compras, passeios, outros | padrão outros |
| descricao | texto | 1–200 caracteres |
| data / hora | data, hora | padrão: momento da mensagem no fuso configurado (America/Sao_Paulo) |

## Requisitos não funcionais

- **Segurança:** webhook valida o header `X-Telegram-Bot-Api-Secret-Token`; apenas IDs em
  `ALLOWED_USER_IDS` podem usar o bot; segredos só via `.env` / `secrets/` (nunca no git).
- **Robustez:** falhas de STT/LLM/Sheets geram mensagens amigáveis e nunca derrubam o
  processo; updates duplicados do Telegram são ignorados; gravação idempotente.
- **Operação:** Docker Compose na EC2, Nginx com TLS (Let's Encrypt) na frente, `/health`.

## Arquitetura v2 (módulos) — ver issue #23

```
mensagem → [Whisper se áudio] → ROTEADOR (Jev; fallback DeepSeek)
  ├─ escrita → extrator (DeepSeek) → Pagamento (parcelas calculadas pela aplicação)
  │            → confirmação → escritor determinístico no formato de config/planilha.yaml
  ├─ leitura → agente de leitura (DeepSeek escolhe a consulta) → consultas determinísticas
  └─ outro   → ajuda
```

| Módulo | Responsabilidade | Task |
|---|---|---|
| `app/domain.py` | regras de valor/moeda/categoria/descrição (base) | T01 |
| `app/telegram_api.py` | cliente da Bot API | T02 |
| `app/stt.py` | transcrição Whisper | T03 |
| `app/extractor.py` | extrator v1 (base de robustez do v2) | T04 |
| `app/pending_store.py` | pendentes em SQLite | T05 |
| `app/sheets.py` | escrita no Sheets (v1 + escritor por schema) | T06, T14 |
| `app/payment.py` | `Pagamento` e cálculo de parcelas | T10 |
| `app/sheet_schema.py` + `config/planilha.yaml` | formato padrão da planilha | T11 |
| `app/router.py` | roteador de intenção (Jev) | T12 |
| `app/payment_extractor.py` | extração de pagamentos | T13 |
| `app/queries.py`, `app/read_agent.py` | caminho de leitura | T15 |
| `app/bot.py` | orquestração do fluxo | T16 |
| `evals/`, `tools/run_evals.py` | avaliação do roteador/extrator | T17 |
| `app/main.py` | FastAPI + webhook + wiring | T08 |
| Docker/Nginx/docs | deploy na EC2 | T09 |

Ordem: T01–T06 → T10 → (T11, T12) → (T13, T14, T15) → T16 → T17 → T08 → T09.
