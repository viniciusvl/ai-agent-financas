# Changelog

## v0.2.1 — 2026-10-21

- Formato padrão da planilha simplificado para 9 colunas: Data, Descrição, Categoria,
  Forma de pagamento, Parcelas, Valor, Valor da parcela, Moeda e ID.

## v0.2.0 — 2026-10-10

O projeto passa a se chamar **ai-agent-financas**: um agente de finanças pessoais **geral**,
que lê e grava gastos numa planilha específica do Google Sheets (T18, #56).

### Mudanças
- **Planilha do dono:** `config/planilha.yaml` é o exemplo a ajustar ao seu modelo; o agente
  segue esse formato para ler e gravar.
- **Padrões:** fuso `America/Sao_Paulo` e moeda `BRL`.
- **Moedas:** BRL, USD e EUR (`€`).
- **Formas de pagamento:** dinheiro, débito, crédito à vista, crédito parcelado, Pix,
  **boleto**, **transferência** (TED/DOC) e outro.
- Prompts, mensagens, documentação, deploy (`deploy/nginx/ai-agent-financas*.conf`) e casos de
  avaliação genéricos (gastos pessoais).
- **Evals** (78 casos gerais, DeepSeek real): rota **100%**, campos **98,6%**.

## v0.1.0 — 2026-10-09

Primeira versão do agente de gastos (arquitetura v2, issue #23).

### Funcionalidades
- **Registro de pagamentos por texto ou áudio** (Telegram → Whisper → DeepSeek), com
  confirmação antes de gravar e parcelas **calculadas pela aplicação** (T10, T13, T16).
- **Roteador de intenção** escrita/leitura/outro com **Jev** (versão fixada) e fallback no
  DeepSeek (T12).
- **Escrita determinística** no Google Sheets, no formato de `config/planilha.yaml`,
  idempotente e com escape de fórmulas (T06, T11, T14).
- **Consultas**: total por período, por categoria, por forma de pagamento, últimos gastos e
  parcelas futuras — números calculados pela aplicação (T15).
- **Webhook** FastAPI com segredo, deduplicação e processamento em background (T08).
- **Deploy** na EC2: Docker Compose, Nginx/HTTPS (bootstrap em duas fases), `set_webhook` e
  guia completo (T09).
- **Evals**: 62 casos reais; primeira execução: rota 100%, campos 99,2% (T17).

### Base
- Telegram (T02), Whisper (T03), extrator v1 (T04), pendentes em SQLite (T05), domínio (T01).

### Processo / infraestrutura
- Spec-driven com testes de aceite escritos antes da implementação; agentes executores
  (opencode + DeepSeek) em loops com revisão do orquestrador (issue #1).
- Runner: escopo por task, pre-push hook, guard de branches, trava de revisão, watchdog de
  inatividade, `stdin` fechado nas sessões.

### Pendências conhecidas
- Decisões provisórias do orquestrador a confirmar (#23): formato da planilha (D2), métodos
  (D4), moeda (D5), consultas (D6).
- `TYPESAFE_API_KEY` (Jev) ainda não configurada — o roteador usa o fallback DeepSeek.
- Credenciais do Google, domínio e EC2 ainda não provisionados.
- Melhorias: #42 (filtros na leitura), #44 (duplo clique em Confirmar).
