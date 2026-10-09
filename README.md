# china-financas-bot

Bot do Telegram para registrar e consultar os gastos da viagem à China numa planilha do
Google Sheets — por texto ou áudio.

```
mensagem (texto/áudio) → Telegram → webhook (EC2 + Nginx + HTTPS) → FastAPI
   → áudio? Whisper (STT)
   → ROTEADOR (Jev; fallback DeepSeek): escrita | leitura | outro
      ├─ escrita → DeepSeek extrai {valor, moeda, método, parcelas, categoria, ...}
      │            → aplicação calcula as parcelas → [✅ Confirmar] [❌ Cancelar]
      │            → linha nova na planilha, no formato de config/planilha.yaml
      ├─ leitura → DeepSeek escolhe a consulta → aplicação calcula → resposta
      └─ outro   → ajuda
```

Exemplos: *"comprei um tênis de 600 reais em 3x no crédito"*, *"paguei 80 kuai no táxi com
WeChat"*, *"quanto gastei esta semana?"*, *"quais parcelas ainda faltam?"*.

## Princípios

- **O LLM não faz contas:** parcelas, totais e datas padrão são calculados pela aplicação.
- **Escrita determinística:** a gravação na planilha é código (sem agente/MCP), idempotente e
  com proteção contra fórmulas.
- **Formato da planilha é configuração:** `config/planilha.yaml` alimenta os prompts e o escritor.
- **Confirmação humana** antes de gravar.

## Stack

- Python 3.12, FastAPI, httpx, pydantic-settings, pyyaml
- [Jev](https://docs.typesafe.ai) (TypeSafe) para roteamento; DeepSeek (`deepseek-flash`)
  para extração, consultas e fallback do roteador
- Whisper (API compatível com a OpenAI) para áudio
- gspread + service account para o Google Sheets; SQLite para pendentes
- Docker Compose + Nginx + Let's Encrypt numa EC2

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `app/` | aplicação (um módulo por responsabilidade — ver `specs/000-produto.md`) |
| `config/planilha.yaml` | formato padrão da planilha |
| `specs/` | especificações (produto + uma spec por task) |
| `tests/acceptance/` | critérios de aceite executáveis das tasks |
| `tests/unit/` | testes unitários |
| `evals/` + `tools/run_evals.py` | avaliação do roteador/extrator com frases reais |
| `tools/agent_loop/` | runner dos agentes executores (opencode + DeepSeek) |
| `deploy/`, `docs/` | deploy e documentação |

## Desenvolvimento

```bash
python -m pip install -r requirements-dev.txt
cp .env.example .env              # preencha as chaves
python -m pytest                  # testes
python -m ruff check . && python -m ruff format --check .
python -m tools.run_evals --check # casos de avaliação (sem rede)
python -m tools.run_evals --live  # avaliação real (usa as chaves do .env)
```

- Deploy: [docs/deploy.md](docs/deploy.md)
- Fluxo de trabalho (spec-driven + agent loops + gitflow): [docs/workflow.md](docs/workflow.md)
