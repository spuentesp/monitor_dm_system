# =============================================================================
# MONITOR CLI — production image
# =============================================================================
# Single-stage: installs data-layer + agents + cli into a venv and exposes
# the `monitor` console script as the entrypoint. Lightweight — no ML deps
# unless the consuming app adds them via runtime env (OLLAMA_* etc).
# Build context is packages/.
# =============================================================================

FROM python:3.11-slim

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY data-layer /build/packages/data-layer
COPY agents     /build/packages/agents
COPY cli        /build/packages/cli

RUN pip install --upgrade pip && \
    pip install /build/packages/data-layer && \
    pip install /build/packages/agents && \
    pip install /build/packages/cli

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH"

# Default command prints the CLI version. Override at `docker run` time with
# e.g. `docker run ghcr.io/<owner>/monitor-cli:latest init --provider ollama`.
ENTRYPOINT ["monitor"]
CMD ["version"]
