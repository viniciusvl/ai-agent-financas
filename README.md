# china-financas-bot

Bot do Telegram para registrar os gastos da viagem à China em uma planilha do Google Sheets.

```
mensagem (texto/áudio) → Telegram → webhook (EC2 + Nginx + HTTPS) → FastAPI
   → áudio? Whisper (STT) → DeepSeek extrai {valor, moeda, categoria, ...}
   → bot pergunta "os dados estão corretos?" [✅ Confirmar] [❌ Cancelar]
   → confirmado → linha nova no Google Sheets
```

## Stack

- Python 3.12, FastAPI, httpx, pydantic-settings
- Whisper (endpoint compatível com a API da OpenAI) para áudio
- DeepSeek (API compatível com a OpenAI) para extrair os dados do gasto
- gspread + service account para o Google Sheets
- SQLite para gastos aguardando confirmação
- Docker Compose + Nginx + Let's Encrypt em uma EC2

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `app/` | código da aplicação (um módulo por responsabilidade) |
| `specs/` | especificações (spec-driven): produto + uma spec por task |
| `tests/acceptance/` | testes de aceite das specs (critérios objetivos das tasks) |
| `tests/unit/` | testes unitários adicionais |
| `tools/agent_loop/` | orquestrador dos agentes executores (opencode + DeepSeek) |
| `.opencode/agent/` | definição do agente executor |
| `deploy/`, `docs/` | deploy e documentação |

## Desenvolvimento

```bash
python -m pip install -r requirements-dev.txt
cp .env.example .env          # preencha as chaves
python -m pytest              # testes (aceite só das tasks concluídas)
python -m ruff check . && python -m ruff format --check .
```

Fluxo de trabalho (gitflow + agent loops): veja [docs/workflow.md](docs/workflow.md).
