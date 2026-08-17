FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AQUANQA_REPO_ROOT=/app

# Se copian solo los dos paquetes necesarios para que el artefacto del dashboard no arrastre
# ETL, API ni el código de la base de datos.
COPY packages/analitica /app/packages/analitica
COPY apps/dashboard /app/apps/dashboard
COPY docs/data /app/docs/data

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir /app/packages/analitica \
    && pip install --no-cache-dir "/app/apps/dashboard[deploy]"

WORKDIR /app/apps/dashboard

EXPOSE 8050

CMD ["gunicorn", "--bind", "0.0.0.0:8050", "--workers", "1", "--threads", "4", "app:server"]
