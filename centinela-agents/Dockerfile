# Centinela · API de agentes antifraude
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# pypdfium2 trae binarios precompilados; no hace falta toolchain de compilación.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Capa de dependencias, separada del código para aprovechar la caché.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --upgrade pip && pip install .

COPY scripts/ ./scripts/
COPY tests/ ./tests/

RUN mkdir -p data/traces data/samples data/synthetic reports \
    && useradd --create-home --uid 1000 centinela \
    && chown -R centinela:centinela /app
USER centinela

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "centinela.main:app", "--host", "0.0.0.0", "--port", "8000"]
