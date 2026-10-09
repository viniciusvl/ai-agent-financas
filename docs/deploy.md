# Deploy do China Finanças Bot na EC2

Passo a passo para colocar o bot em produção numa instância **EC2 (Ubuntu)** com
**Docker**, **Nginx** terminando o TLS (Let's Encrypt/`certbot`) e o webhook do
Telegram registrado no domínio público.

Ao longo deste guia, substitua o placeholder **`bot.SEU-DOMINIO.com`** pelo
domínio real do bot.

## 1. EC2

1. Crie uma instância **Ubuntu** (24.04 LTS recomendado) na AWS, tipo `t3.small`
   ou superior (Whisper/DeepSeek são chamadas externas, mas há tráfego de áudio).
2. No **Security Group**, libere as portas **22 (SSH)**, **80 (HTTP)** e
   **443 (HTTPS)** para a internet. A porta **8000 não deve** ser exposta: o
   container só a publica em `127.0.0.1` e o Nginx faz o proxy.
3. Acesse via SSH e instale o Docker + o plugin do Compose:

   ```bash
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl git
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker "$USER"
   ```

   Saia e entre de novo na sessão SSH para o grupo `docker` valer.
4. Clone o repositório; a produção acompanha a branch `main`:

   ```bash
   git clone <url-do-repositorio> china-financas-bot
   cd china-financas-bot
   git checkout main
   ```

## 2. DNS

1. No seu provedor de DNS, crie um registro **A** apontando
   `bot.SEU-DOMINIO.com` para o **IP público (Elastic IP)** da EC2.
2. (Opcional) Crie também o registro `www` como alias do mesmo IP.
3. Confirme a propagação antes de seguir (o `certbot` precisa que o domínio já
   resolva para o servidor):

   ```bash
   dig +short bot.SEU-DOMINIO.com
   ```

## 3. Docker

1. Crie o arquivo `.env` na raiz do projeto (não versione): veja a seção
   [6. Variáveis de ambiente](#6-variáveis-de-ambiente).
2. Crie as pastas de dados e a de segredos:

   ```bash
   mkdir -p data secrets
   ```

3. Construa e suba o container:

   ```bash
   docker compose up -d --build
   ```

   O Compose executa o serviço `bot` a partir do `Dockerfile`
   (`python:3.12-slim`, usuário não-root `app`), com `restart: unless-stopped`,
   o healthcheck em `http://127.0.0.1:8000/health` e os volumes
   `./data` (banco SQLite), `./secrets` (credenciais Google, somente leitura) e
   `./config` (schema da planilha, somente leitura, editável sem rebuild).
4. Acompanhe os logs e o status:

   ```bash
   docker compose logs -f bot
   docker compose ps
   curl -fsS http://127.0.0.1:8000/health
   ```

## 4. Nginx e HTTPS

O certificado é emitido com `certbot certonly --webroot`, então o Nginx precisa
estar no ar servindo o desafio ACME **antes** de existir HTTPS. Por isso o
bootstrap do TLS é feito em duas fases: primeiro um bloco somente HTTP (porta 80),
depois a config completa com TLS.

1. Instale o Nginx e o `certbot`:

   ```bash
   sudo apt-get install -y nginx certbot
   ```

2. **Fase 1 — config somente HTTP (porta 80).** Habilite
   `china-financas-bot.http-only.conf`, que serve `/.well-known/acme-challenge/`
   para o desafio, ajuste o domínio, valide e suba o Nginx:

   ```bash
   sudo cp deploy/nginx/china-financas-bot.http-only.conf \
     /etc/nginx/sites-available/china-financas-bot.conf
   sudo sed -i 's/bot.SEU-DOMINIO.com/SEU-DOMINIO-REAL.com/g' \
     /etc/nginx/sites-available/china-financas-bot.conf
   sudo ln -sf /etc/nginx/sites-available/china-financas-bot.conf \
     /etc/nginx/sites-enabled/china-financas-bot.conf
   sudo rm -f /etc/nginx/sites-enabled/default
   sudo nginx -t
   sudo systemctl reload nginx
   ```

3. Emita o certificado apontando para o `webroot`. O `--deploy-hook` fica salvo
   na renovação e recarrega o Nginx a cada renovação:

   ```bash
   sudo mkdir -p /var/www/certbot
   sudo certbot certonly --webroot -w /var/www/certbot \
     -d bot.SEU-DOMINIO.com \
     --deploy-hook "systemctl reload nginx"
   ```

4. **Fase 2 — config completa com TLS.** Agora que os certificados existem,
   substitua a config e recarregue:

   ```bash
   sudo cp deploy/nginx/china-financas-bot.conf \
     /etc/nginx/sites-available/china-financas-bot.conf
   sudo sed -i 's/bot.SEU-DOMINIO.com/SEU-DOMINIO-REAL.com/g' \
     /etc/nginx/sites-available/china-financas-bot.conf
   sudo nginx -t
   sudo systemctl reload nginx
   ```

   O Nginx expõe publicamente apenas `location /telegram/webhook` e
   `location /health` (proxy para `127.0.0.1:8000`); qualquer outra rota retorna
   `404`. O HTTP é redirecionado para HTTPS com `return 301`.

5. Teste o redirect e o health:

   ```bash
   curl -I https://bot.SEU-DOMINIO.com/health
   ```

6. A renovação já é agendada pelo pacote do `certbot`
   (`systemctl list-timers | grep certbot`); o `--deploy-hook` do passo 3
   recarrega o Nginx automaticamente após renovar. Valide o fluxo com:

   ```bash
   sudo certbot renew --dry-run
   ```

## 5. Google Sheets

1. No **Google Cloud Console**, crie um projeto e habilite a **Google Sheets API**
   e a **Google Drive API**.
2. Crie uma **conta de serviço** e gere uma **chave JSON**. Salve o arquivo como
   `secrets/google-service-account.json` na raiz do projeto — ele é montado em
   `/app/secrets/google-service-account.json` (somente leitura).
3. Abra o JSON e copie o campo `client_email`
   (algo como `bot@projeto.iam.gserviceaccount.com`).
4. **Compartilhe a planilha com o e-mail da conta de serviço** com permissão de
   **Editor** — sem isso o bot não consegue ler nem escrever.
5. Copie o **ID da planilha** (trecho entre `/d/` e `/edit` na URL) para a
   variável `GOOGLE_SHEET_ID`. O nome da aba **não** é variável de ambiente: ele
   vem do campo `aba:` em `config/planilha.yaml` (padrão `Gastos`) — ajuste ali
   se a planilha usar outro nome.

## 6. Variáveis de ambiente

Crie o arquivo `.env` na raiz do projeto (não versionado; o `.dockerignore` já o
exclui da imagem). Exemplo:

```dotenv
# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_WEBHOOK_SECRET=uma-string-secreta-aleatoria
PUBLIC_BASE_URL=https://bot.SEU-DOMINIO.com
ALLOWED_USER_IDS=11111111,22222222

# Whisper (STT)
WHISPER_API_KEY=...
WHISPER_BASE_URL=
WHISPER_MODEL=whisper-1
WHISPER_LANGUAGE=pt

# DeepSeek (extração)
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash

# Jev / TypeSafe (roteador de intenção)
TYPESAFE_API_KEY=...
JEV_MODEL=jev-1.13.0
JEV_BASE_URL=https://api.typesafe.ai
ROUTER_CONFIDENCE_THRESHOLD=0.6

# Schema da planilha
SHEET_SCHEMA_PATH=config/planilha.yaml

# Google Sheets
GOOGLE_SERVICE_ACCOUNT_FILE=secrets/google-service-account.json
GOOGLE_SHEET_ID=...

# App
TIMEZONE=Asia/Shanghai
DEFAULT_CURRENCY=CNY
DB_PATH=data/bot.db
PENDING_TTL_SECONDS=86400
LOG_LEVEL=INFO
```

Reinicie o container para aplicar: `docker compose up -d`.

## 7. Registrar o webhook

Com o domínio apontando para a EC2 e o HTTPS ativo, registre o webhook no
Telegram a partir de dentro da EC2 (ou de qualquer máquina com o mesmo `.env`):

```bash
docker compose exec bot python -m scripts.set_webhook
```

Ou, com o ambiente local instalado:

```bash
python -m scripts.set_webhook
```

O script lê `PUBLIC_BASE_URL` e `TELEGRAM_WEBHOOK_SECRET` do `.env` e chama
`set_webhook("https://bot.SEU-DOMINIO.com/telegram/webhook", <secret>)`. Ele
retorna erro se `PUBLIC_BASE_URL` ou `TELEGRAM_WEBHOOK_SECRET` estiverem vazios.

Confira o estado do webhook na API do Telegram:

```bash
curl -s "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

## 8. Atualizar a aplicação

Para publicar uma nova versão:

```bash
cd china-financas-bot
git pull
docker compose up -d --build
docker compose logs -f bot
```

O banco (`./data`) e as credenciais (`./secrets`) persistem entre rebuilds. Se o
formato da planilha mudar, basta editar `config/planilha.yaml` e reiniciar o
container (`docker compose restart bot`) — não é necessário rebuild.
