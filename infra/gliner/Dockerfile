# Self-hosted GLiNER NER service for MONITOR.
#
# Replaces the upstream knowledgator/gliner-base image, whose availability is
# unreliable. The model is baked into the image at build time so runtime startup
# is hermetic (HF_HUB_OFFLINE=1) and does not depend on Hugging Face availability.
#
# Build:
#   docker build -t monitor-gliner --build-arg MODEL_NAME=urchade/gliner_base infra/gliner
# (docker-compose builds this automatically via the gliner profile.)
#
# 2026-11-09: the former default, knowledgator/gliner-base-v0.1, returns
# 401 "Repository Not Found" from Hugging Face and can no longer be baked in;
# urchade/gliner_base is the canonical upstream GLiNER base model.

FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

# CPU-only torch keeps the image small; install it first so its index is not
# mixed with PyPI for the remaining deps.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# gliner 0.2.21's _from_pretrained() still requires the `proxies`/
# `resume_download` kwargs that huggingface_hub >= 0.26 stopped passing —
# pin the hub client to the last compatible line or the model load crashes
# with "missing 2 required keyword-only arguments".
RUN pip install --no-cache-dir "gliner==0.2.21" "huggingface_hub==0.25.2" "fastapi>=0.108" "uvicorn[standard]>=0.27"

# Bake the model into the image (build-time download must be ONLINE — the
# offline flags below only apply at runtime). The GLiNER snapshot is flattened
# into /model for server.py, and the transformer backbone named in
# gliner_config.json (microsoft/deberta-v3-base for urchade/gliner_base) is
# fetched into the HF hub cache so transformers can resolve it offline at
# runtime.
ARG MODEL_NAME=urchade/gliner_base
ARG BACKBONE_NAME=microsoft/deberta-v3-base
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('${MODEL_NAME}', local_dir='/model'); snapshot_download('${BACKBONE_NAME}')"

# Runtime is hermetic: no Hugging Face calls after build.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY server.py /app/server.py
WORKDIR /app

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
