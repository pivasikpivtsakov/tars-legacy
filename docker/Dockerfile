FROM python:3.14-slim

ENV APP_USER=appuser \
    APP_GROUP=appgroup \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev python3-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir uv

RUN groupadd --system "$APP_GROUP" \
    && useradd -m --system "$APP_USER" --groups "$APP_GROUP"

WORKDIR /app

COPY . .

RUN chown -R "$APP_USER":"$APP_GROUP" /app

USER $APP_USER

RUN uv sync --frozen --no-dev \
    && pybabel compile -d locales -D bot
