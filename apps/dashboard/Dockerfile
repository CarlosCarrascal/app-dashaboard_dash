FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AQUANQA_REPO_ROOT=/app

COPY packages/analitica /app/packages/analitica
COPY apps/dashboard /app/apps/dashboard
COPY docs/data /app/docs/data

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir /app/packages/analitica \
    && pip install --no-cache-dir "/app/apps/dashboard[deploy]"

WORKDIR /app/apps/dashboard

EXPOSE 10000

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 app:server"]