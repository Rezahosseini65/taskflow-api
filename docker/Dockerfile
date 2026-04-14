# =========================
# 1️⃣ Builder Stage
# =========================
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.5 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# نصب وابستگی‌ها - بدون retry mechanism پیچیده
RUN poetry install --no-interaction --no-ansi --with dev --no-root

# =========================
# 2️⃣ Runtime Stage
# =========================
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    DEBIAN_FRONTEND=noninteractive

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy project files
COPY --chown=appuser:appuser scripts/ /app/scripts/
COPY --chown=appuser:appuser src/ /app/src/

RUN chmod +x /app/scripts/entrypoint.dev.sh && \
    sed -i 's/\r$//' /app/scripts/entrypoint.dev.sh

USER appuser

EXPOSE 8000

CMD ["/app/scripts/entrypoint.dev.sh"]