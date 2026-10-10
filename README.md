# ai-agent-financas

Agente de IA no Telegram que **lê e grava seus gastos numa planilha específica do Google
Sheets**: registre pagamentos por texto ou áudio e consulte totais, categorias e parcelas.
O modelo da planilha é seu — o agente segue o formato descrito em `config/planilha.yaml`.

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

Exemplos: *"comprei um tênis de 600 reais em 3x no crédito"*, *"paguei 80 reais no mercado com
pix"*, *"quanto gastei esta semana?"*, *"quais parcelas ainda faltam?"*.

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
| `config/planilha.yaml` | formato da **sua** planilha (ajuste ao seu modelo) |
| `specs/` | especificações (produto + uma spec por task) |
| `tests/acceptance/` | critérios de aceite executáveis das tasks |
| `tests/unit/` | testes unitários |
| `evals/` + `tools/run_evals.py` | avaliação do roteador/extrator com frases reais |
| `tools/agent_loop/` | runner dos agentes executores (opencode + DeepSeek) |
| `deploy/`, `docs/` | deploy e documentação |

## Sua planilha

Crie a planilha com o seu modelo e descreva-o em `config/planilha.yaml` (nome da aba,
colunas na ordem, tipo e formato de cada uma). O agente usa esse arquivo para entender a
planilha ao responder perguntas e para gravar novas linhas; ao iniciar, ele confere se o
cabeçalho da aba bate com o arquivo e não grava nada se houver divergência.

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
