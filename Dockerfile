# Imagem do china-financas-bot. Ver specs/tasks/T09-deploy.md
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependências primeiro (aproveita o cache de camadas do Docker).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Código da aplicação, scripts utilitários e o schema da planilha (config/planilha.yaml).
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY config/ ./config/

# Usuário não-root; os diretórios de dados/segredos são montados por volume.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data /app/secrets \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
