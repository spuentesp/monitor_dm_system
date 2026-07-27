# =============================================================================
# MONITOR agents — production image
# =============================================================================
# Multi-stage: builder installs data-layer then agents into a venv; final
# stage copies only the venv. Build context is packages/.
# =============================================================================

FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY data-layer /build/packages/data-layer
COPY agents     /build/packages/agents

RUN pip install --upgrade pip && \
    pip install /build/packages/data-layer && \
    pip install /build/packages/agents

# =============================================================================
FROM python:3.11-slim AS final

WORKDIR /app

# Runtime libs only (drop build-essential, keep libpq5)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# No default CMD — operators invoke `python -m monitor_agents.<module>` or
# extend this image in compose. Keeping it minimal makes the image reusable.
