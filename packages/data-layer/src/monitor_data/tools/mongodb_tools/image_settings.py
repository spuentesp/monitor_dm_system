"""Image-generation settings persistence (Task 10, Layer 1).

A single MongoDB document with ``_id="global"`` stores the per-deployment
UI overrides. The two operations:

- :func:`mongodb_get_image_generation_settings` — return the merged
  settings (env defaults from :mod:`monitor_data.config` with the
  Mongo singleton's overrides layered on top).
- :func:`mongodb_update_image_generation_settings` — upsert the
  singleton with the supplied :class:`ImageGenerationSettings` and
  return the merged view.

The merge is per-field. The Mongo singleton is best-effort: when it's
absent (deployments that never touched the UI, fresh DB), the env
defaults win. This matches the brief's "merged over environment
defaults" contract.

Pydantic bounds live on the schema (``Field(ge=0, le=100)`` etc.).
Constructing an :class:`ImageGenerationSettings` with an out-of-range
value raises ``ValueError`` synchronously — the router (and any
caller) handles it before sending the document to Mongo.

LAYER: 1 (data-layer)
IMPORTS FROM: monitor_data internal modules + external libraries only
"""

from __future__ import annotations

from datetime import UTC, datetime

from monitor_data.config import settings
from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.image_settings import ImageGenerationSettings

_COLLECTION = "image_generation_settings"
_SINGLETON_ID = "global"


def _coerce_overrides(doc: dict[str, object] | None) -> dict[str, object]:
    """Pull the override fields out of a Mongo singleton document.

    The shape on disk is the same as the schema field names; we drop
    ``_id`` and any bookkeeping so the merge step can't see them.
    """
    if not doc:
        return {}
    return {key: value for key, value in doc.items() if key != "_id"}


def _env_defaults() -> ImageGenerationSettings:
    """Build an :class:`ImageGenerationSettings` from the live env defaults."""
    return ImageGenerationSettings(
        image_moderation_mode=settings.image_moderation_mode,
        image_max_per_scene=settings.image_max_per_scene,
        image_max_per_conversation=settings.image_max_per_conversation,
        image_max_per_actor_hour=settings.image_max_per_actor_hour,
        image_suggestions_enabled=settings.image_suggestions_enabled,
    )


def mongodb_get_image_generation_settings() -> ImageGenerationSettings:
    """Return the merged image-generation settings.

    The Mongo singleton (if present) wins per-field over the env defaults
    baked into :class:`monitor_data.config.Settings`. When the singleton
    is absent (fresh install / cleared), the env defaults are returned
    verbatim.
    """
    coll = get_mongodb_client().get_collection(_COLLECTION)
    document = coll.find_one({"_id": _SINGLETON_ID})
    merged = {**_env_defaults().model_dump(), **_coerce_overrides(document)}
    return ImageGenerationSettings.model_validate(merged)


def mongodb_update_image_generation_settings(
    params: ImageGenerationSettings,
) -> ImageGenerationSettings:
    """Upsert the supplied settings on the singleton and return the merged view.

    The PUT endpoint accepts a partial :class:`ImageGenerationSettings`
    (callers send only the fields they want to change). We use
    ``exclude_unset=True`` so untouched fields stay as they were on the
    singleton — merging with the env defaults only happens on the next
    read.

    The caller is expected to construct ``params`` from validated input
    (the FastAPI route handler does this via the request model). Out-of-
    range values fail before we reach this function.
    """
    now = datetime.now(UTC)
    coll = get_mongodb_client().get_collection(_COLLECTION)
    updates = params.model_dump(exclude_unset=True)
    if not updates:
        # Empty payload (no fields set) — still surface the merged view
        # so the round-trip response is consistent.
        return mongodb_get_image_generation_settings()
    updates["updated_at"] = now
    coll.update_one(
        {"_id": _SINGLETON_ID},
        {"$set": updates},
        upsert=True,
    )
    return mongodb_get_image_generation_settings()


__all__ = [
    "mongodb_get_image_generation_settings",
    "mongodb_update_image_generation_settings",
]
