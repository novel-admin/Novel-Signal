FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY pyproject.toml README.md ./
COPY apps/backend/src ./apps/backend/src
RUN pip install --no-cache-dir . && playwright install --with-deps chromium

COPY apps ./apps
COPY infra ./infra

EXPOSE 8000
CMD ["uvicorn", "novel_signal.main:app", "--app-dir", "apps/backend/src", "--host", "0.0.0.0", "--port", "8000"]
