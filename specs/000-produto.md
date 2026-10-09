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

## Arquitetura (módulos)

| Módulo | Responsabilidade | Task |
|---|---|---|
| `app/domain.py` | modelo `Expense`, normalização, formatação | T01 |
| `app/telegram_api.py` | cliente da Bot API | T02 |
| `app/stt.py` | transcrição Whisper | T03 |
| `app/extractor.py` | extração com DeepSeek | T04 |
| `app/pending_store.py` | pendentes em SQLite | T05 |
| `app/sheets.py` | Google Sheets | T06 |
| `app/bot.py` | orquestração do fluxo | T07 |
| `app/main.py` | FastAPI + webhook + wiring | T08 |
| Docker/Nginx/docs | deploy na EC2 | T09 |

Ordem/dependências: T01 → (T02, T03, T04, T05, T06 — independentes entre si, executadas em sequência) → T07 → T08 → T09.
