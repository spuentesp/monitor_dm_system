# =============================================================================
# MONITOR UI Backend — production image
# =============================================================================
# Multi-stage build: builder installs all deps into a venv, final stage copies
# only the venv and source so the image stays lean.
# =============================================================================

FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for compilation (psycopg2, lxml, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create isolated venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy all three package layers in dependency order so pip can resolve editable installs
# Build context is packages/ (set in docker-compose) so paths are relative to that.
COPY data-layer /build/packages/data-layer
COPY agents     /build/packages/agents
COPY ui/backend /build/packages/ui/backend

# Install data-layer, then agents, then ui-backend.
# NOTE: non-editable installs — editable (-e) writes absolute /build paths into
# the venv, which break when the venv is copied into the final stage.
RUN pip install --upgrade pip && \
    pip install /build/packages/data-layer && \
    pip install /build/packages/agents && \
    pip install /build/packages/ui/backend

# =============================================================================
FROM python:3.11-slim AS final

WORKDIR /app

# Runtime system libs only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder (packages are installed into site-packages; no source
# trees needed in the final image)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Working directory for uvicorn (config.py looks for .env here — overridden by
# explicit env vars in docker-compose so this is only a local fallback path)
WORKDIR /app

EXPOSE 8001

CMD ["sh", "-c", "uvicorn monitor_ui.main:app --host ${UI_HOST:-0.0.0.0} --port ${UI_PORT:-8000} --log-level info"]
