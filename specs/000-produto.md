# Spec de produto — china-financas-bot

## Objetivo

Registrar, com o mínimo de atrito, todos os gastos de uma viagem à China em uma planilha do
Google Sheets, a partir de mensagens de texto ou áudio enviadas a um bot do Telegram.

## Fluxo principal

1. Usuário autorizado envia ao bot um **texto** ("gastei 35 kuai no almoço, alipay") ou um
   **áudio** (voice note ou arquivo de áudio).
2. O Telegram entrega o update via **webhook HTTPS** ao servidor (EC2, domínio próprio).
3. Se for áudio, o servidor baixa o arquivo e transcreve com **Whisper**; o bot responde com a
   transcrição.
4. O texto é enviado ao **DeepSeek**, que devolve JSON estruturado do gasto.
5. O bot responde com o resumo do gasto e os botões **✅ Confirmar** / **❌ Cancelar**. O gasto
   fica pendente (SQLite) por até 24 h.
6. Ao confirmar, o gasto é inserido como nova linha na planilha e a mensagem é editada para
   "✅ Gasto registrado!". Ao cancelar, o pendente é descartado.

## Dados de um gasto

| Campo | Tipo | Regra |
|---|---|---|
| amount | Decimal | > 0, 2 casas decimais |
| currency | CNY / BRL / USD | padrão CNY |
| category | alimentação, transporte, hospedagem, compras, passeios, outros | padrão outros |
| description | texto | 1–200 caracteres |
| payment_method | dinheiro, cartão, alipay, wechat, outro | padrão outro |
| spent_at | data | padrão: hoje no fuso Asia/Shanghai |
| raw_text | texto | mensagem/transcrição original |

Colunas da planilha: Data, Descrição, Categoria, Valor, Moeda, Pagamento, Usuário,
Registrado em, Texto original.

## Requisitos não funcionais

- **Segurança:** webhook valida o header `X-Telegram-Bot-Api-Secret-Token`; apenas IDs em
  `ALLOWED_USER_IDS` podem usar o bot; segredos só via `.env` / `secrets/` (nunca no git).
- **Robustez:** falhas de STT/LLM/Sheets geram mensagens amigáveis e nunca derrubam o
  processo; updates duplicados do Telegram são ignorados.
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
