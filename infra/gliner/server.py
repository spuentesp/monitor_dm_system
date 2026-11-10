"""Minimal GLiNER NER HTTP server, API-compatible with monitor_data.db.gliner.

Endpoints:
    GET  /health           -> {"status": "ok", "model": ...}
    POST /predict          -> {"entities": [{text, label, start, end, confidence}]}
    POST /predict_batch    -> {"results": [{"entities": [...]}, ...]}

The model is baked into the image at /model (see Dockerfile); GLINER_MODEL is
only used as a fallback when /model is absent (e.g. local debugging).
"""

import os

from fastapi import FastAPI
from gliner import GLiNER
from pydantic import BaseModel

MODEL_DIR = "/model"
MODEL_NAME = os.getenv("GLINER_MODEL", "urchade/gliner_base")
MAX_LENGTH = int(os.getenv("GLINER_MAX_LENGTH", "384"))

_load_path = MODEL_DIR if os.path.isdir(MODEL_DIR) else MODEL_NAME
model = GLiNER.from_pretrained(_load_path)
model.config.max_len = MAX_LENGTH

app = FastAPI(title="gliner-ner")


class PredictRequest(BaseModel):
    text: str
    labels: list[str]
    threshold: float = 0.5


class BatchPredictRequest(BaseModel):
    texts: list[str]
    labels: list[str]
    threshold: float = 0.5


def _to_entity(raw: dict) -> dict:
    return {
        "text": raw["text"],
        "label": raw["label"],
        "start": raw["start"],
        "end": raw["end"],
        "confidence": raw.get("score", 0.0),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL_NAME, "max_length": MAX_LENGTH}


@app.post("/predict")
def predict(req: PredictRequest) -> dict:
    if not req.text.strip():
        return {"entities": []}
    raw = model.predict_entities(req.text, req.labels, threshold=req.threshold)
    return {"entities": [_to_entity(e) for e in raw]}


@app.post("/predict_batch")
def predict_batch(req: BatchPredictRequest) -> dict:
    results = []
    for text in req.texts:
        if not text.strip():
            results.append({"entities": []})
            continue
        raw = model.predict_entities(text, req.labels, threshold=req.threshold)
        results.append({"entities": [_to_entity(e) for e in raw]})
    return {"results": results}
