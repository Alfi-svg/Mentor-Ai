# ==============================================================================
# Mentor AI — Multi-Stage Production Dockerfile for FastAPI Backend
# Lightweight, secure, non-root execution compatible with Render / Container hosts
# ==============================================================================

# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Minimal runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/mentor/.local/bin:${PATH}" \
    PORT=8000 \
    HOST=0.0.0.0

# Install runtime PostgreSQL client library
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 10001 mentor && \
    useradd -u 10001 -g mentor -m -s /bin/bash mentor

# Copy installed Python packages from builder
COPY --from=builder --chown=mentor:mentor /root/.local /home/mentor/.local

# Copy application source code
COPY --chown=mentor:mentor alembic.ini .
COPY --chown=mentor:mentor alembic ./alembic
COPY --chown=mentor:mentor app ./app

USER mentor

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/v1/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
