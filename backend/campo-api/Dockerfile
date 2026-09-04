FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY backend/campo-api /app/backend/campo-api
RUN python -m pip install --no-cache-dir /app/backend/campo-api

EXPOSE 8000
CMD ["uvicorn", "aquanqa_campo_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
