# =============================================================================
# MONITOR data-layer — production image
# =============================================================================
# Single-stage: inherits only the data-layer's declared deps. The other two
# Python packages (agents, cli) build on top of this image.
# Build context is packages/ (set in the publish workflow).
# =============================================================================

FROM python:3.11-slim

WORKDIR /build

# System deps for compiled packages (psycopg2, lxml, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create isolated venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy package source and install
COPY data-layer /build/packages/data-layer
RUN pip install --upgrade pip && \
    pip install /build/packages/data-layer

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH"

# No ENTRYPOINT — this image is consumed by downstream Dockerfiles (agents,
# cli, ui-backend) which COPY site-packages from this stage.
