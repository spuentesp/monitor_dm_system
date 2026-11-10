# Self-hosted GLiNER NER service for MONITOR.
#
# Replaces the upstream knowledgator/gliner-base image, whose availability is
# unreliable. The model is baked into the image at build time so runtime startup
# is hermetic (HF_HUB_OFFLINE=1) and does not depend on Hugging Face availability.
#
# Build:
#   docker build -t monitor-gliner --build-arg MODEL_NAME=knowledgator/gliner-base-v0.1 infra/gliner
# (docker-compose builds this automatically via the gliner profile.)

FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/model \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# CPU-only torch keeps the image small; install it first so its index is not
# mixed with PyPI for the remaining deps.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir "gliner==0.2.21" "fastapi>=0.108" "uvicorn[standard]>=0.27"

# Bake the model into the image.
ARG MODEL_NAME=knowledgator/gliner-base-v0.1
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('${MODEL_NAME}')"

COPY server.py /app/server.py
WORKDIR /app

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
