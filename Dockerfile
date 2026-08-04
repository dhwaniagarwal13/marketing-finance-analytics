# Multi-stage: build the frontend with Node, run everything from Python.
# The Node layer never reaches the final image.

# --- frontend ---------------------------------------------------------------
FROM node:20-alpine AS web
WORKDIR /web
# Copy manifests first so `npm ci` is cached until dependencies actually change.
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- runtime ----------------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY analytics/ ./analytics/
COPY api/ ./api/

# Installs the engine plus [web] only. Notebook and plotting extras are
# excluded on purpose: no matplotlib, no plotly, no kaleido, therefore no
# headless Chromium in a public-facing image.
RUN pip install --no-cache-dir ".[web]"

# The demo dataset ships with the image. It is generated, seeded, and ~3.5 MB,
# so baking it in avoids a runtime fetch and keeps the container stateless.
COPY data/raw/campaigns.csv data/raw/customers.csv \
     data/raw/transactions.csv data/raw/ab_test_campaigns.csv \
     ./data/raw/

COPY --from=web /web/dist ./static

# Run unprivileged.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/api/health')"

# Single worker on purpose: the simulation ticker and the in-memory dataset
# store are per-process state. Scaling out needs shared state first, and at
# this size one process is not the bottleneck.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
