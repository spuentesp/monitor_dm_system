"""Two reuse layers for finished Analyzer batches (I-17, I-8).

1. **Saved batches** (MongoDB, ``book_records`` for the document): every
   successful model call is stored under its prompt key, so a rescan or a
   resume of the same file with the same settings reuses it instead of paying
   for the call again. The records hang off ``doc_id`` — deliberately not the
   job row, because a rescan deletes the source's job rows before rerunning,
   which is exactly why a rescan used to repeat every call.

2. **Disk cache** (one JSON file per key): the second layer, off unless
   ``MONITOR_ANALYZER_LLM_CACHE=1``, keyed by model, prompt and settings, and
   stored outside the repository (``~/.cache/monitor/analyzer-llm`` by default;
   a directory that sits inside a git checkout is refused).

Both layers share one key: model + signature instructions + module kwargs +
the batching settings hash. A failure in either layer degrades to a cache miss —
reuse can never break an analysis — and a store that has already failed once is
not retried on every call.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from monitor_data.schemas.book_graph import BookRecord, BookRecordType
from monitor_data.tools.mongodb_tools.book_decomposition import (
    mongodb_list_book_records,
    mongodb_upsert_book_records,
)

from monitor_agents.analyzer import _settings

logger = logging.getLogger(__name__)

_RECORD_PREFIX = "analyzer-batch:"
# A single absurdly large reply is not worth a job-document slot; the model
# will be called again for it rather than risk bloating Mongo.
_MAX_PAYLOAD_BYTES = 512 * 1024
_KEY_SEPARATOR = "\x1f"


def prompt_key(
    *,
    model: str | None,
    stage: str,
    instructions: str,
    kwargs: dict[str, Any],
) -> str:
    """Fingerprint one model call: model, prompt (instructions + inputs), settings."""
    try:
        prompt = json.dumps(kwargs, sort_keys=True, default=str)
    except (TypeError, ValueError):
        prompt = repr(sorted(kwargs.items()))
    payload = _KEY_SEPARATOR.join(
        [
            model or "unknown-model",
            stage,
            instructions,
            prompt,
            _settings.settings_hash(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prediction_to_jsonable(value: Any) -> dict[str, Any]:
    """JSON-safe fields of a dspy Prediction (or any dict-like result)."""
    if hasattr(value, "toDict"):
        raw = value.toDict()
    elif isinstance(value, dict):
        raw = dict(value)
    else:
        raise TypeError(f"cannot serialize {type(value).__name__}")
    return {str(name): _jsonable(item) for name, item in raw.items()}


def prediction_from_jsonable(payload: dict[str, Any], signature: Any) -> Any:
    """Rebuild a dspy Prediction, re-validating output fields against the signature.

    Raises when an output field is missing or no longer validates, so a stale
    or corrupt cache entry becomes a plain cache miss instead of a wrong typed
    result.
    """
    import dspy
    from pydantic import TypeAdapter

    outputs = dict(getattr(signature, "output_fields", None) or {})
    missing = [name for name in outputs if name not in payload]
    if missing:
        raise ValueError(f"saved batch is missing output fields: {', '.join(sorted(missing))}")
    fields: dict[str, Any] = {}
    for name, raw in payload.items():
        info = outputs.get(name)
        annotation = getattr(info, "annotation", None) if info is not None else None
        if annotation is None:
            fields[name] = raw
            continue
        fields[name] = TypeAdapter(annotation).validate_python(raw)
    return dspy.Prediction(**fields)


def _jsonable(item: Any) -> Any:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if isinstance(item, (list, tuple)):
        return [_jsonable(entry) for entry in item]
    if isinstance(item, dict):
        return {str(key): _jsonable(val) for key, val in item.items()}
    if item is None or isinstance(item, (str, int, float, bool)):
        return item
    raise TypeError(f"cannot serialize {type(item).__name__}")


def payload_size(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, default=str).encode("utf-8"))


class AnalyzerBatchStore:
    """Saved Analyzer batches for one document, scoped to the current settings.

    The document's REPORT records are read once per run and kept in memory:
    listing them for every model call would re-fetch the whole report set
    (including a decomposition's graphs) on each batch.
    """

    def __init__(self, doc_id: str | None) -> None:
        self._doc_id = doc_id or ""
        self._settings = _settings.settings_hash()
        self._broken = False
        self._index: dict[str, dict[str, Any]] | None = None
        self.reused = 0  # successful reuses this run (for the job's activity log)

    @property
    def enabled(self) -> bool:
        return bool(self._doc_id)

    def _record_key(self, key: str) -> str:
        return f"{_RECORD_PREFIX}{self._settings}:{key}"

    def _load(self) -> dict[str, dict[str, Any]] | None:
        if self._broken:
            return None
        if self._index is not None:
            return self._index
        try:
            records = mongodb_list_book_records(self._doc_id, BookRecordType.REPORT)
        except Exception as exc:  # noqa: BLE001  # reason: reuse is optional; a dead DB must not fail the analysis
            self._broken = True
            logger.warning("analyzer_batch_store_unavailable: %s", exc)
            return None
        self._index = {
            record.key: record.data
            for record in records
            if record.key.startswith(f"{_RECORD_PREFIX}{self._settings}:")
            and isinstance(record.data, dict)
            and isinstance(record.data.get("payload"), dict)
        }
        return self._index

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        index = self._load()
        if index is None:
            return None
        entry = index.get(self._record_key(key))
        if entry is None:
            return None
        self.reused += 1
        payload: dict[str, Any] | None = entry["payload"]
        return payload

    def put(self, key: str, payload: dict[str, Any]) -> None:
        if not self.enabled or self._broken:
            return
        try:
            too_big = payload_size(payload) > _MAX_PAYLOAD_BYTES
        except (TypeError, ValueError):
            return  # unserializable payload: skip saving, the store is fine
        if too_big:
            logger.debug("analyzer_batch_too_large_to_save key=%s", key[:12])
            return
        record_key = self._record_key(key)
        try:
            mongodb_upsert_book_records(
                self._doc_id,
                BookRecordType.REPORT,
                [
                    BookRecord(
                        key=record_key,
                        data={"payload": payload, "saved_at": datetime.now(UTC).isoformat()},
                    )
                ],
            )
        except Exception as exc:  # noqa: BLE001  # reason: reuse is optional; a dead DB must not fail the analysis
            self._broken = True
            logger.warning("analyzer_batch_store_write_failed: %s", exc)
            return
        if self._index is not None:
            self._index[record_key] = {"payload": payload}


class ResponseDiskCache:
    """Disk layer for model responses; off unless MONITOR_ANALYZER_LLM_CACHE=1."""

    def __init__(self, root: Path | None = None, *, enabled: bool | None = None) -> None:
        self._enabled = _settings.llm_cache_enabled() if enabled is None else enabled
        self._root = root if root is not None else _settings.llm_cache_dir()
        self._resolved = False
        self._broken = False

    @property
    def enabled(self) -> bool:
        if not self._enabled:
            return False
        if not self._resolved:
            self._resolved = True
            if self._inside_repository(self._root):
                logger.warning(
                    "analyzer_llm_cache_dir_inside_repository_refused dir=%s — using the default outside the repo",
                    self._root,
                )
                self._root = _settings.DEFAULT_CACHE_DIR
        return True

    @staticmethod
    def _inside_repository(path: Path) -> bool:
        """Refuse a cache directory that sits inside a git checkout."""
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            return False
        for candidate in (resolved, *resolved.parents):
            if (candidate / ".git").exists():
                return True
        return False

    def _path(self, key: str) -> Path:
        return self._root / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled or self._broken:
            return None
        path = self._path(key)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            self._broken = True
            logger.warning("analyzer_llm_cache_unreadable: %s", exc)
            return None
        try:
            doc = json.loads(raw)
            payload = doc.get("payload") if isinstance(doc, dict) else None
            return payload if isinstance(payload, dict) else None
        except (ValueError, TypeError) as exc:
            logger.warning("analyzer_llm_cache_corrupt key=%s: %s", key[:12], exc)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None

    def put(self, key: str, payload: dict[str, Any]) -> None:
        if not self.enabled or self._broken:
            return
        try:
            body = json.dumps(
                {
                    "payload": payload,
                    "key": key,
                    "saved_at": datetime.now(UTC).isoformat(),
                },
                default=str,
            )
        except (TypeError, ValueError):
            return  # unserializable payload: skip caching, the cache is fine
        if len(body.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
            return
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(body, encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            self._broken = True
            logger.warning("analyzer_llm_cache_write_failed: %s", exc)
