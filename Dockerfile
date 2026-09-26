# syntax=docker/dockerfile:1

# ---- frontend -------------------------------------------------------------- #
FROM node:24-alpine AS frontend
WORKDIR /app/apps/nova
COPY apps/nova/package.json apps/nova/package-lock.json ./
RUN npm ci
COPY apps/nova ./
RUN npm run build

# ---- runtime --------------------------------------------------------------- #
FROM python:3.12-slim AS runtime

# curl is used by the container healthcheck only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    NOVA_ENV=production \
    NOVA_DATABASE_URL=sqlite:////data/nova.db \
    NOVA_SPA_DIST_DIR=/app/apps/nova/dist

WORKDIR /app
COPY pyproject.toml README.md ./
COPY services/api ./services/api
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY --from=frontend /app/apps/nova/dist ./apps/nova/dist
COPY docker/entrypoint.sh /usr/local/bin/nova-entrypoint
RUN chmod +x /usr/local/bin/nova-entrypoint

# Run as an unprivileged user; /data is the only writable path it needs.
RUN useradd --system --uid 10001 --home /app nova \
    && mkdir -p /data \
    && chown -R nova:nova /app /data
USER nova
VOLUME ["/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health/ready || exit 1

ENTRYPOINT ["nova-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
